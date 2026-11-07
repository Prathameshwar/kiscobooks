"""Resume accepted Simple products and Advanced openings with fresh Identity authority.

Run as a separately supervised process. A short poll is a wake fallback; each
native command and its idempotency key remain durable in the creation row.
"""

import asyncio
import datetime as dt
import logging
import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError
from billing_platform.outbox import audit_payload, emit
from billing_platform.service_auth import CompanyServiceScope
from pydantic import Field
from sqlalchemy import select

from catalog.config import Settings
from catalog.main import create_app
from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks import advanced_creation_opening, simple_product_creation
from catalog.tasks.identity_source import IdentitySourceSettings, fetch_enrollments
from catalog.tasks.simple_creation_authority import fetch_context
from catalog.tasks.simple_creation_preparation import creation_permissions
from catalog.tasks.simple_creation_transport import CreationOwners

logger = logging.getLogger(__name__)


class WorkerSettings(Settings):
    identity_source: IdentitySourceSettings
    source_subscriptions: tuple[CompanyServiceScope, ...] = Field(default=(), max_length=1000)
    source_discovery: bool = True
    creation_poll_seconds: float = Field(default=2, ge=1, le=30)


def due(progress: dict[str, Any]) -> bool:
    value = progress.get("worker_retry_at")
    if not value:
        return True
    try:
        return dt.datetime.fromisoformat(value) <= utcnow()
    except (ValueError, TypeError):
        return True


async def defer(
    factory: Any, scope: CompanyServiceScope, kind: str, identity: uuid.UUID,
    item_id: uuid.UUID | None, error: Exception,
) -> None:
    model = SimpleProductCreation if kind == "simple" else AdvancedProductCreation
    with tenant_scope(scope.tenant_id):
        async with factory.begin() as db:
            row = await db.scalar(select(model).where(
                model.company_id == scope.company_id, model.id == identity
            ).with_for_update())
            if row is None or row.status == "COMPLETE" or (
                row.lease_expires_at is not None and row.lease_expires_at > utcnow()
            ):
                return
            progress = dict(row.progress)
            if item_id is not None:
                skus = dict(progress.get("skus", {}))
                entry = dict(skus.get(str(item_id), {}))
                if entry.get("opening_state") != "IN_PROGRESS":
                    return
                target = dict(entry.get("opening_progress", {}))
            else:
                target = progress
            attempt = min(int(target.get("worker_attempt", 0)) + 1, 6)
            target["worker_attempt"] = attempt
            target["worker_retry_at"] = (
                utcnow() + dt.timedelta(seconds=min(60, 2 ** attempt))
            ).isoformat()
            target["last_error"] = (
                str(error)[:500] if isinstance(error, PlatformError)
                else "Product creation is temporarily unavailable; retry is scheduled"
            )
            if item_id is not None:
                entry["opening_progress"] = target
                entry["opening_error"] = target["last_error"]
                skus[str(item_id)] = entry
                progress["skus"] = skus
            row.progress = progress
            row.row_version += 1
            event = f"catalog.{model.__tablename__}.defer"
            emit(
                db, tenant_id=scope.tenant_id, aggregate_type=f"catalog.{model.__tablename__}",
                aggregate_id=identity, event_type=event,
                payload=audit_payload(
                    action=event, category="admin", entity_type=f"catalog.{model.__tablename__}",
                    entity_id=identity, actor_user_id=None, company_id=scope.company_id,
                    reason="Durable product creation will retry after an owner or authority error",
                ) | {"actor_type": "system", "source_service": "catalog"},
            )


async def work_scope(app: Any, settings: WorkerSettings, scope: CompanyServiceScope) -> int:
    factory = app.state.session_factory
    # Failed attempts update the row, so oldest-update order rotates deferred jobs
    # behind untouched jobs even when one company has more than a page of work.
    with tenant_scope(scope.tenant_id):
        async with factory() as db:
            simple = list(await db.scalars(
                select(SimpleProductCreation).where(
                    SimpleProductCreation.company_id == scope.company_id,
                    SimpleProductCreation.status == "RUNNING",
                ).order_by(SimpleProductCreation.updated_at, SimpleProductCreation.id).limit(20)
            ))
            advanced = list(await db.scalars(
                select(AdvancedProductCreation).where(
                    AdvancedProductCreation.company_id == scope.company_id,
                    AdvancedProductCreation.status == "OPENING",
                ).order_by(AdvancedProductCreation.updated_at, AdvancedProductCreation.id).limit(20)
            ))
    candidates: list[tuple[str, uuid.UUID, uuid.UUID, dict[str, Any], uuid.UUID | None]] = []
    for row in simple:
        if due(row.progress) and (row.lease_expires_at is None or row.lease_expires_at <= utcnow()):
            candidates.append(("simple", row.id, row.created_by, row.request, None))
    for row in advanced:
        if row.lease_expires_at is not None and row.lease_expires_at > utcnow():
            continue
        for item in row.sku_ids:
            entry = row.progress.get("skus", {}).get(item, {})
            if (
                entry.get("opening_state") == "IN_PROGRESS"
                and due(entry.get("opening_progress", {}))
            ):
                candidates.append(("advanced", row.id, row.owner_user_id,
                                   entry["opening_request"], uuid.UUID(item)))
                break
    if not candidates:
        return 0
    kind, identity, user, request, item_id = candidates[0]
    body = SimpleCreationInput.model_validate(request)
    permissions = creation_permissions(body) if kind == "simple" else (
        creation_permissions(body) - {"item.create", "item.activate"}
    )
    try:
        actor, context, headers = await fetch_context(
            settings.identity_source,
            settings.actor_signing_secret.get_secret_value().encode(),
            scope.tenant_id, scope.company_id, user, permissions,
        )
        owners = CreationOwners(
            app, headers, settings.simple_creation_origins, settings.voucher_source_delivery
        )
        if item_id is None:
            await simple_product_creation.drive(factory, actor, context, identity, owners)
        else:
            await advanced_creation_opening.advance(
                factory, actor, context, identity, item_id, owners
            )
        return 1
    except Exception as error:
        logger.warning("Product creation deferred: %s", type(error).__name__)
        await defer(factory, scope, kind, identity, item_id, error)
        return 0


async def serve(settings: WorkerSettings) -> None:
    app = create_app(settings)
    scopes = settings.source_subscriptions
    refresh_at = dt.datetime.min.replace(tzinfo=dt.UTC)
    try:
        while True:
            if settings.source_discovery and utcnow() >= refresh_at:
                try:
                    discovered = await fetch_enrollments(settings.identity_source)
                    scopes = tuple({
                        (s.tenant_id, s.company_id): s
                        for s in (*settings.source_subscriptions, *discovered)
                    }.values())
                    refresh_at = utcnow() + dt.timedelta(seconds=30)
                except Exception as error:
                    logger.warning("Creation enrollment refresh deferred: %s", type(error).__name__)
                    refresh_at = utcnow() + dt.timedelta(seconds=10)
            for scope in scopes:
                try:
                    await work_scope(app, settings, scope)
                except Exception as error:
                    logger.warning("Creation scope deferred: %s", type(error).__name__)
            await asyncio.sleep(settings.creation_poll_seconds)
    finally:
        await app.state.engine.dispose()


def main() -> None:
    asyncio.run(serve(WorkerSettings()))  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
