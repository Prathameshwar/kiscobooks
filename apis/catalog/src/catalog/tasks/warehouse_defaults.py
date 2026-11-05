"""Idempotent Main/transit defaults from verified company enrollment facts."""

import uuid
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from billing_platform.db.base import Base
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import changes
from catalog.models.projections import CompanyProjection
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.projections import require_identity_context
from catalog.tasks.unit_defaults import inventory_enabled
from catalog.tasks.warehouse_foundation import locations, policies

Row = TypeVar("Row", bound=Base)


@dataclass
class WarehouseDefaultsResult:
    status: Literal["READY", "NOT_APPLICABLE"]
    created_records: int = 0


async def ensure_warehouse_defaults(
    db: AsyncSession, company: uuid.UUID
) -> WarehouseDefaultsResult:
    """Trusted source worker only; no fabricated user and no authored location data."""
    tenant = require_current_tenant()
    checkpoint = await require_identity_context(db, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None:
        raise ConflictError("verified company settings are unavailable")
    if profile.status != "active" or not await inventory_enabled(db, company):
        return WarehouseDefaultsResult("NOT_APPLICABLE")
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    result = WarehouseDefaultsResult("READY")

    async def create(model: type[Row], /, **values: Any) -> Row:
        identity = uuid7()
        row = model(id=identity, tenant_id=tenant, company_id=company, row_version=1, **values)
        entity = "catalog." + model.__tablename__
        event = audit_event(entity, "create")
        payload = audit_payload(
            action=event,
            category=category(entity, "create"),
            entity_type=entity,
            entity_id=identity,
            actor_user_id=None,
            company_id=company,
            changes=changes(entity, frozenset(values), after=values, creating=True),
            reason="warehouse-defaults-v1",
        )
        payload.update(actor_type="system", source_service="catalog")
        db.add(row)
        emit(
            db,
            tenant_id=tenant,
            aggregate_type=entity,
            aggregate_id=identity,
            event_type=event,
            payload=payload,
        )
        await db.flush()
        result.created_records += 1
        return row

    configuration = await locations(
        db,
        company,
        timezone=profile.timezone,
        source_version=checkpoint.source_version,
        create=create,
    )
    await policies(db, company, configuration, create)
    if result.created_records:
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation exhausted")
        state.generation += 1
        await db.flush()
    return result
