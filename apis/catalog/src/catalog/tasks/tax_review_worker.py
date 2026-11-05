"""Run separately with python -m catalog.tasks.tax_review_worker; no startup migrations.

Advances pending tax impact reviews one bounded chunk at a time. Actor proofs are fetched
outside every database transaction; the durable checkpoint on the review row provides
correctness after a restart, and the in-memory cursor only round-robins between reviews.
"""

import asyncio
import logging
import uuid

from billing_platform.actor_authorization import ActorAuthorizationProof
from billing_platform.command_transaction import command_transaction
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.service_auth import CompanyServiceScope
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.tax_governance import TaxImpactReview
from catalog.tasks.actor_authorization import fetch_actor_authorization
from catalog.tasks.bulk_execution import PERMISSION_CHUNKS, current_actor
from catalog.tasks.identity_source import IdentitySourceSettings
from catalog.tasks.tax_impact_reviews import MAX_CHUNK, chunk, fail

logger = logging.getLogger(__name__)


class TaxReviewWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    identity_source: IdentitySourceSettings
    source_subscriptions: tuple[CompanyServiceScope, ...] = Field(min_length=1, max_length=1000)
    tax_review_chunk_size: int = Field(default=MAX_CHUNK, ge=1, le=MAX_CHUNK, strict=True)
    tax_review_poll_seconds: int = Field(default=3, ge=1, le=60, strict=True)


async def step(
    factory: async_sessionmaker[AsyncSession],
    proofs: tuple[ActorAuthorizationProof, ...],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    review_id: uuid.UUID,
    *,
    limit: int = MAX_CHUNK,
) -> str:
    """One chunk as the review's requester, authorized by fresh proofs; returns the status."""
    async with command_transaction(
        factory, tenant_id=tenant, company_id=company, actor_id=user
    ) as db:
        actor = await current_actor(db, proofs, tenant, company, user)
        review = await chunk(db, actor, company, review_id, limit=limit)
        return review.status


async def stop(
    factory: async_sessionmaker[AsyncSession],
    subscription: CompanyServiceScope,
    review_id: uuid.UUID,
    version: int,
) -> None:
    with tenant_scope(subscription.tenant_id):
        async with factory.begin() as db:
            await fail(db, subscription.company_id, review_id, version, "actor_denied")


async def run_once(
    factory: async_sessionmaker[AsyncSession],
    settings: TaxReviewWorkerSettings,
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID],
) -> int:
    processed = 0
    for subscription in settings.source_subscriptions:
        scope = subscription.tenant_id, subscription.company_id
        with tenant_scope(subscription.tenant_id):
            async with factory.begin() as db:
                stmt = (
                    select(
                        TaxImpactReview.id,
                        TaxImpactReview.actor_user_id,
                        TaxImpactReview.row_version,
                    )
                    .where(
                        TaxImpactReview.company_id == subscription.company_id,
                        TaxImpactReview.status == "PENDING",
                    )
                    .order_by(TaxImpactReview.id)
                    .limit(1)
                )
                selected = None
                if scope in cursors:
                    selected = (
                        await db.execute(stmt.where(TaxImpactReview.id > cursors[scope]))
                    ).one_or_none()
                if selected is None:
                    selected = (await db.execute(stmt)).one_or_none()
        if selected is None:
            cursors.pop(scope, None)
            continue
        cursors[scope] = selected.id
        try:
            # Network context is closed before the chunk transaction starts.
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
            await step(
                factory,
                proofs,
                subscription.tenant_id,
                subscription.company_id,
                selected.actor_user_id,
                selected.id,
                limit=settings.tax_review_chunk_size,
            )
            processed += 1
        except PermissionDeniedError:
            await stop(factory, subscription, selected.id, selected.row_version)
            logger.warning("Catalog tax review stopped: actor denied")
        except (ConflictError, ValidationFailedError) as exc:
            # A review that left PENDING concurrently; the next traversal skips it.
            logger.warning("Catalog tax review chunk skipped: %s", type(exc).__name__)
        except Exception as exc:
            # Source/network/database failures leave the durable checkpoint unchanged.
            logger.warning("Catalog tax review chunk deferred: %s", type(exc).__name__)
    return processed


async def serve(settings: TaxReviewWorkerSettings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    try:
        while True:
            try:
                processed = await run_once(factory, settings, cursors)
            except Exception as exc:
                logger.warning("Catalog tax review traversal deferred: %s", type(exc).__name__)
                processed = 0
            if not processed:
                await asyncio.sleep(settings.tax_review_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(serve(TaxReviewWorkerSettings()))  # type: ignore[call-arg] # Settings come from the environment.


if __name__ == "__main__":
    main()
