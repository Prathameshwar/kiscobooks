"""Tenant self-service — reading and updating the actor's own tenant.

A tenant user only ever sees their own tenant, so this is a singleton at ``/v1/tenant``
rather than a collection: the id is the actor's ``tenant_id`` and the session filter
(``SelfTenantMixin``, matched on ``id``) makes another tenant's row unreachable.

Platform tenant provisioning — creating, listing across tenants, suspending — is a
separate platform-ops surface that runs under ``unfiltered()`` with ``platform.*``
permissions, and is intentionally not part of this tenant-facing API.
"""

from __future__ import annotations

from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError
from billing_platform.outbox import emit
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Tenant
from identity.schemas.tenant import TenantDetail, TenantUpdate
from identity.services.tenant_provisioning import validate_defaults

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute, prefix="/v1")

_TENANT = ScopePath()


async def _load_tenant(db: AsyncSession, tenant_id: Any) -> Tenant:
    row = await db.get(Tenant, tenant_id)
    if row is None:
        raise NotFoundError("tenant not found")
    return row


@router.get("/tenant", response_model=TenantDetail)
async def get_tenant(
    current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Tenant:
    current.require("tenant.read")
    current.require_scope("tenant.read", target=_TENANT)
    return await _load_tenant(db, current.tenant_id)


@router.patch("/tenant", response_model=TenantDetail)
async def update_tenant(
    body: TenantUpdate, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Tenant:
    current.require("tenant.update")
    current.require_scope("tenant.update", target=_TENANT)
    row = await _load_tenant(db, current.tenant_id)

    incoming = body.model_dump(exclude_unset=True)
    if any(
        key in incoming
        for key in (
            "default_country_code",
            "default_state_code",
            "default_currency_code",
            "default_timezone",
            "default_locale",
        )
    ):
        await validate_defaults(
            db,
            incoming.get("default_country_code", row.default_country_code),
            incoming.get("default_currency_code", row.default_currency_code),
            incoming.get("default_timezone", row.default_timezone),
            incoming.get("default_locale", row.default_locale),
            incoming.get("default_state_code", row.default_state_code),
        )

    changes: dict[str, dict[str, Any]] = {}
    for name, value in incoming.items():
        before = getattr(row, name)
        if before != value:
            changes[name] = {"from": before, "to": value}
            setattr(row, name, value)
    if changes:
        row.updated_at = utcnow()
        row.updated_by = current.user_id
        emit(
            db,
            aggregate_type="tenant",
            aggregate_id=row.id,
            event_type="tenant.updated",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                action="tenant.updated",
                entity_type="tenant",
                entity_id=row.id,
                actor_user_id=current.user_id,
                category="admin",
                changes=changes,
            ),
        )
        await db.flush()
    return row
