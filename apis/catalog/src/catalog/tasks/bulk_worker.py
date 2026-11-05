"""Run separately with python -m catalog.tasks.bulk_worker; no startup migrations."""

import asyncio
import logging
import uuid
from typing import cast

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.service_auth import CompanyServiceScope
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import (
    BulkChangeSet,
    BulkChangeSetEffect,
    BulkImportArtifact,
    BulkJob,
    BulkJobRecord,
)
from catalog.tasks.actor_authorization import fetch_actor_authorization
from catalog.tasks.bulk_execution import PERMISSION_CHUNKS, step
from catalog.tasks.bulk_jobs import audit, touch
from catalog.tasks.identity_source import IdentitySourceSettings, IdentitySourceUnavailableError
from catalog.tasks.policy_state import company_policy_state

logger = logging.getLogger(__name__)


class BulkWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    identity_source: IdentitySourceSettings
    actor_signing_secret: SecretStr
    source_subscriptions: tuple[CompanyServiceScope, ...] = Field(min_length=1, max_length=1000)
    bulk_poll_seconds: int = Field(default=2, ge=1, le=60, strict=True)
    bulk_chunk_seconds: int = Field(default=25, ge=1, le=25, strict=True)


async def stop_job(
    factory: async_sessionmaker[AsyncSession],
    subscription: CompanyServiceScope,
    job_id: uuid.UUID,
    version: int,
    reason: str = "review_required",
) -> None:
    with tenant_scope(subscription.tenant_id):
        async with factory.begin() as db:
            await company_policy_state(
                db, subscription.tenant_id, subscription.company_id, lock=True
            )
            job = await db.scalar(
                select(BulkJob)
                .where(BulkJob.company_id == subscription.company_id, BulkJob.id == job_id)
                .with_for_update()
            )
            if (
                job is None
                or job.row_version != version
                or job.state not in {"VALIDATING", "QUEUED", "RUNNING"}
            ):
                return
            actor = Actor(tenant_id=subscription.tenant_id, user_id=job.actor_user_id, grants=())
            job.state, job.selection_digest = ("PARTIAL" if job.completed_count else "FAILED"), None
            models: tuple[type[BulkChangeSet] | type[BulkJobRecord], ...] = (
                BulkChangeSet,
                BulkJobRecord,
            )
            for model in models:
                pending = list(
                    await db.scalars(
                        select(model)
                        .where(
                            model.company_id == subscription.company_id,
                            model.job_id == job.id,
                            model.state.in_(("STAGED", "VALID")),
                        )
                        .limit(2000)
                    )
                )
                for pending_row in pending:
                    row = cast(BulkChangeSet | BulkJobRecord, pending_row)
                    row.state, row.error_code = "BLOCKED", reason
                if model is BulkJobRecord:
                    job.invalid_count += len(pending)
            touch(job, actor)
            audit(db, actor, job)


async def expire_artifacts(
    factory: async_sessionmaker[AsyncSession], subscription: CompanyServiceScope
) -> int:
    with tenant_scope(subscription.tenant_id):
        async with factory.begin() as db:
            await company_policy_state(
                db, subscription.tenant_id, subscription.company_id, lock=True
            )
            rows = list(
                await db.scalars(
                    select(BulkImportArtifact)
                    .where(
                        BulkImportArtifact.company_id == subscription.company_id,
                        BulkImportArtifact.expires_at <= utcnow(),
                        BulkImportArtifact.byte_count > 0,
                    )
                    .order_by(BulkImportArtifact.expires_at, BulkImportArtifact.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            for row in rows:
                row.content, row.byte_count = b"", 0
                row.row_version += 1
                row.updated_at, row.updated_by = utcnow(), None
                job = await db.scalar(
                    select(BulkJob)
                    .where(BulkJob.company_id == subscription.company_id, BulkJob.id == row.job_id)
                    .with_for_update()
                )
                assert job is not None
                payloads = await db.scalars(
                    select(BulkJobRecord)
                    .where(
                        BulkJobRecord.company_id == subscription.company_id,
                        BulkJobRecord.job_id == job.id,
                    )
                    .limit(2000)
                )
                for payload in payloads:
                    (
                        payload.normalized_input,
                        payload.prepared_input,
                        payload.preview,
                        payload.source_pins,
                    ) = {}, None, None, None
                effects = await db.scalars(
                    select(BulkChangeSetEffect)
                    .where(
                        BulkChangeSetEffect.company_id == subscription.company_id,
                        BulkChangeSetEffect.job_id == job.id,
                    )
                    .limit(2000)
                )
                for effect in effects:
                    effect.results, effect.source_pins = {}, []
                actor = Actor(
                    tenant_id=subscription.tenant_id, user_id=job.actor_user_id, grants=()
                )
                if job.state in {"VALIDATING", "QUEUED", "RUNNING", "READY", "STAGED"}:
                    job.state = "PARTIAL" if job.completed_count else "FAILED"
                job.selection_digest, job.selected_keys = None, None
                touch(job, actor)
                audit(db, actor, job)
            return len(rows)


async def run_once(
    factory: async_sessionmaker[AsyncSession],
    settings: BulkWorkerSettings,
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID],
) -> int:
    processed = 0
    for subscription in settings.source_subscriptions:
        scope = subscription.tenant_id, subscription.company_id
        # Retention must progress even while this company has a busy queue.
        await expire_artifacts(factory, subscription)
        with tenant_scope(subscription.tenant_id):
            async with factory.begin() as db:
                stmt = (
                    select(BulkJob.id, BulkJob.actor_user_id, BulkJob.row_version)
                    .where(
                        BulkJob.company_id == subscription.company_id,
                        BulkJob.state.in_(("VALIDATING", "QUEUED", "RUNNING")),
                    )
                    .order_by(BulkJob.id)
                    .limit(1)
                )
                if scope in cursors:
                    selected = (
                        await db.execute(stmt.where(BulkJob.id > cursors[scope]))
                    ).one_or_none()
                else:
                    selected = None
                if selected is None:
                    selected = (await db.execute(stmt)).one_or_none()
        if selected is None:
            cursors.pop(scope, None)
            continue
        cursors[scope] = selected.id
        try:
            # Signed proof acquisition is outside every DB transaction. No job
            # stores grants or accepts actor/proof material from its upload.
            proofs = tuple(
                await asyncio.gather(
                    *(
                        fetch_actor_authorization(
                            settings.identity_source,
                            tenant_id=subscription.tenant_id,
                            company_id=subscription.company_id,
                            user_id=selected.actor_user_id,
                            permissions=permissions,
                        )
                        for permissions in PERMISSION_CHUNKS
                    )
                )
            )
            remaining = (min(proof.expires_at for proof in proofs) - utcnow()).total_seconds() - 1
            try:
                async with asyncio.timeout(max(0, min(settings.bulk_chunk_seconds, remaining))):
                    processed += await step(
                        factory,
                        proofs,
                        subscription.tenant_id,
                        subscription.company_id,
                        selected.actor_user_id,
                        selected.id,
                        settings.actor_signing_secret.get_secret_value().encode(),
                    )
            except TimeoutError:
                await stop_job(
                    factory, subscription, selected.id, selected.row_version, "chunk_timeout"
                )
            except IdentitySourceUnavailableError:
                if any(proof.expires_at <= utcnow() for proof in proofs):
                    await stop_job(
                        factory, subscription, selected.id, selected.row_version, "chunk_timeout"
                    )
                else:
                    raise
        except (PermissionDeniedError, ConflictError, ValidationFailedError):
            await stop_job(factory, subscription, selected.id, selected.row_version)
        except Exception as exc:
            # Network/database failures leave the durable checkpoint unchanged.
            logger.warning("Catalog bulk chunk deferred: %s", type(exc).__name__)
    return processed


async def serve(settings: BulkWorkerSettings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    try:
        while True:
            try:
                processed = await run_once(factory, settings, cursors)
            except Exception as exc:
                logger.warning("Catalog bulk supervisor deferred: %s", type(exc).__name__)
                processed = 0
            if not processed:
                await asyncio.sleep(settings.bulk_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(serve(BulkWorkerSettings()))  # type: ignore[call-arg] # Settings come from the environment.


if __name__ == "__main__":
    main()
