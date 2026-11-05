"""Fixed, audited starter price plan from verified company enrollment facts."""

import json
import uuid
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Literal, TypeVar

from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import changes
from catalog.models.pricing import PriceLevel, PricePlan, PricingRow
from catalog.models.projections import CompanyProjection
from catalog.schemas.pricing import PlanCreate
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.projections import require_identity_context

Row = TypeVar("Row", bound=PricingRow)


@dataclass
class PricingDefaultsResult:
    status: Literal["READY", "NOT_APPLICABLE", "NEEDS_REVIEW"]
    created_records: int = 0


async def ensure_pricing_defaults(db: AsyncSession, company: uuid.UUID) -> PricingDefaultsResult:
    """Trusted source worker only; this creates definitions, never product rates."""
    tenant = require_current_tenant()
    await require_identity_context(db, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None:
        raise ConflictError("verified company settings are unavailable")
    if profile.status != "active":
        return PricingDefaultsResult("NOT_APPLICABLE")
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    level = await db.scalar(
        select(PriceLevel).where(
            PriceLevel.company_id == company,
            PriceLevel.ordinal == 1,
        )
    )
    if level is not None and not level.is_active:
        return PricingDefaultsResult("NEEDS_REVIEW")
    sale = None
    if level is not None:
        sale = await db.scalar(
            select(PricePlan).where(
                PricePlan.company_id == company,
                PricePlan.price_level_id == level.id,
                PricePlan.currency == profile.base_currency,
            )
        )
    purchase = await db.scalar(
        select(PricePlan)
        .where(
            PricePlan.company_id == company,
            PricePlan.purpose == "PURCHASE",
            PricePlan.currency == profile.base_currency,
        )
        .order_by(PricePlan.id)
        .limit(1)
    )
    pack = json.loads(
        files("catalog.seeds").joinpath("company_pricing_defaults_v1.json").read_text("utf-8")
    )
    for purpose, existing in (("SALE", sale), ("PURCHASE", purchase)):
        if (
            existing is None
            and await db.scalar(
                select(PricePlan.id).where(
                    PricePlan.company_id == company,
                    func.lower(PricePlan.code) == pack[purpose]["code"].lower(),
                )
            )
            is not None
        ):
            return PricingDefaultsResult("NEEDS_REVIEW")
    reserved_level = level is None and await db.scalar(
        select(PriceLevel.id).where(
            PriceLevel.company_id == company,
            func.lower(PriceLevel.code) == "price1",
        )
    )
    if reserved_level:
        return PricingDefaultsResult("NEEDS_REVIEW")
    if sale is not None and purchase is not None:
        return PricingDefaultsResult("READY")
    result = PricingDefaultsResult("READY")

    async def create(model: type[Row], **values: Any) -> Row:
        identity = uuid7()
        row = model(id=identity, tenant_id=tenant, company_id=company, row_version=1, **values)
        db.add(row)
        await db.flush()
        entity = "catalog." + row.__tablename__
        event = audit_event(entity, "create")
        payload = audit_payload(
            action=event,
            category=category(entity, "create"),
            entity_type=entity,
            entity_id=identity,
            actor_user_id=None,
            company_id=company,
            changes=changes(entity, frozenset(values), after=values, creating=True),
            reason="company-pricing-defaults-v1",
        )
        payload.update(actor_type="system", source_service="catalog")
        emit(
            db,
            tenant_id=tenant,
            aggregate_type=entity,
            aggregate_id=identity,
            event_type=event,
            payload=payload,
        )
        result.created_records += 1
        return row

    if level is None:
        level = await create(PriceLevel, code="PRICE1", name="Price 1", ordinal=1, is_active=True)
    for purpose, existing in (("SALE", sale), ("PURCHASE", purchase)):
        if existing is None:
            values = PlanCreate.model_validate(
                {
                    **pack[purpose],
                    "price_level_id": level.id if purpose == "SALE" else None,
                    "currency": profile.base_currency,
                }
            ).model_dump()
            await create(PricePlan, **values)
    if state.generation >= 2**63 - 1:
        raise ConflictError("company policy generation exhausted")
    state.generation += 1
    await db.flush()
    return result
