"""Scoped, restartable custom-index worker; no migration or seed at startup.

Run python -m catalog.tasks.index_worker separately. Acquire actor proofs outside
chunk transactions. In-memory round-robin cursors provide fairness only; durable
job checkpoints and generation locks provide correctness after restart.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.service_auth import CompanyServiceScope as Subscription
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.field_indexes import FieldIndexState, FieldRebuildJob
from catalog.tasks.actor_authorization import fetch_actor_authorization
from catalog.tasks.identity_source import IdentitySourceSettings
from catalog.tasks.index_rebuilds import audit, build_chunk, cleanup_chunk, permissions, scoped_job
from catalog.tasks.policy_state import company_policy_state

logger = logging.getLogger(__name__)


class IndexWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    identity_source: IdentitySourceSettings
    source_subscriptions: tuple[Subscription, ...] = Field(min_length=1, max_length=1000)
    index_chunk_size: int = Field(default=25, ge=1, le=100, strict=True)
    index_poll_seconds: int = Field(default=3, ge=1, le=60, strict=True)


async def fail_build(
    factory: async_sessionmaker[AsyncSession],
    subscription: Subscription,
    entity: str,
    key: str,
    job_id: uuid.UUID,
    expected_version: int,
    reason: str,
) -> None:
    if reason not in {"actor_denied", "definition_changed", "invalid_owner_value"}:
        raise ValueError("invalid private failure code")
    with tenant_scope(subscription.tenant_id):
        async with factory.begin() as db:
            await company_policy_state(
                db, subscription.tenant_id, subscription.company_id, lock=True
            )
            row, state = await scoped_job(
                db, subscription.company_id, entity, key, job_id, lock=True
            )
            if (
                row.row_version != expected_version
                or row.phase != "build"
                or state.building_generation != row.generation
            ):
                return
            row.status, row.phase, row.reason_code = "failed", "cleanup", reason
            row.row_version += 1
            row.updated_at = utcnow()
            row.updated_by = None
            state.retired_generation, state.building_generation, state.building_digest = (
                row.generation,
                None,
                None,
            )
            state.row_version += 1
            state.updated_by = None
            audit(db, subscription.tenant_id, subscription.company_id, row, "failed", actor_id=None)


async def run_once(
    factory: async_sessionmaker[AsyncSession],
    settings: IndexWorkerSettings,
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID],
) -> int:
    processed = 0
    for subscription in settings.source_subscriptions:
        scope_key = (subscription.tenant_id, subscription.company_id)
        with tenant_scope(subscription.tenant_id):
            async with factory.begin() as db:
                stmt = (
                    select(
                        FieldRebuildJob.id,
                        FieldRebuildJob.actor_user_id,
                        FieldRebuildJob.row_version,
                        FieldRebuildJob.phase,
                        FieldIndexState.entity_type,
                        FieldIndexState.field_key,
                    )
                    .join(FieldIndexState, FieldIndexState.id == FieldRebuildJob.state_id)
                    .where(
                        FieldRebuildJob.company_id == subscription.company_id,
                        FieldIndexState.company_id == subscription.company_id,
                        FieldRebuildJob.phase.in_(("build", "cleanup")),
                    )
                    .order_by(FieldRebuildJob.id)
                    .limit(1)
                )
                if scope_key in cursors:
                    stmt = stmt.where(FieldRebuildJob.id > cursors[scope_key])
                row = (await db.execute(stmt)).one_or_none()
        if row is None:
            cursors.pop(scope_key, None)
            continue
        cursors[scope_key] = row.id
        try:
            if row.phase == "cleanup":
                with tenant_scope(subscription.tenant_id):
                    async with factory.begin() as db:
                        await cleanup_chunk(
                            db,
                            tenant=subscription.tenant_id,
                            company=subscription.company_id,
                            entity=row.entity_type,
                            key=row.field_key,
                            job_id=row.id,
                        )
            else:
                # Network context is closed before the business transaction starts.
                proof = await fetch_actor_authorization(
                    settings.identity_source,
                    tenant_id=subscription.tenant_id,
                    company_id=subscription.company_id,
                    user_id=row.actor_user_id,
                    permissions=permissions(row.entity_type),
                )
                with tenant_scope(subscription.tenant_id):
                    async with factory.begin() as db:
                        await build_chunk(
                            db,
                            proof,
                            company=subscription.company_id,
                            entity=row.entity_type,
                            key=row.field_key,
                            job_id=row.id,
                            limit=settings.index_chunk_size,
                        )
            processed += 1
        except (PermissionDeniedError, ConflictError, ValidationFailedError, ValueError) as exc:
            if row.phase == "build":
                reason = (
                    "actor_denied"
                    if isinstance(exc, PermissionDeniedError)
                    else "definition_changed"
                    if isinstance(exc, ConflictError)
                    else "invalid_owner_value"
                )
                await fail_build(
                    factory,
                    subscription,
                    row.entity_type,
                    row.field_key,
                    row.id,
                    row.row_version,
                    reason,
                )
            logger.warning("Catalog index chunk stopped: %s", type(exc).__name__)
        except Exception as exc:
            # A source/network/database failure never extends authority or advances
            # the checkpoint. Move to the next job and retry on the next traversal.
            logger.warning("Catalog index chunk deferred: %s", type(exc).__name__)
    return processed


async def serve(settings: IndexWorkerSettings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    try:
        while True:
            try:
                await run_once(factory, settings, cursors)
            except Exception as exc:
                logger.warning("Catalog index traversal deferred: %s", type(exc).__name__)
            await asyncio.sleep(settings.index_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    # Required settings are resolved from the namespaced environment.
    asyncio.run(serve(IndexWorkerSettings()))  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
