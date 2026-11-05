"""Minimal published defaults for a verified company with no authored product setup."""

import datetime as dt
import json
import uuid
from importlib.resources import files
from typing import Any, TypeVar

from billing_platform.db.base import Base
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import changes
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.configuration import (
    ProductConfigurationDraft,
    ProductConfigurationRevision,
    ProductConfigurationScope,
)
from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.models.pricing import CompanyPricingPolicy, PriceLevel, PricePlan
from catalog.models.product_authoring import CompanyProductAuthoringConfiguration
from catalog.models.products import ProductFamily
from catalog.models.projections import CompanyProjection
from catalog.schemas.configuration import CompanyDraftInput
from catalog.tasks.company_product_defaults import ProductDefaultsResult, existing_default
from catalog.tasks.configuration_access import CHILDREN
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.projections import require_identity_context
from catalog.tasks.unit_defaults import inventory_enabled

Row = TypeVar("Row", bound=Base)
REASON = "company-product-configuration-defaults-v1"
BASELINE_DATE = dt.date(1000, 1, 1)


async def ensure_configuration_defaults(
    db: AsyncSession, company: uuid.UUID
) -> ProductDefaultsResult:
    """The source worker owns this system action; it never grants actor permissions."""
    tenant = require_current_tenant()
    await require_identity_context(db, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None:
        raise ConflictError("verified company settings are unavailable")
    if profile.status != "active":
        return ProductDefaultsResult("NOT_APPLICABLE")
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    scope = await db.scalar(
        select(ProductConfigurationScope).where(
            ProductConfigurationScope.company_id == company,
            ProductConfigurationScope.scope_kind == "COMPANY",
        )
    )
    pricing_policy = await db.scalar(
        select(CompanyPricingPolicy.id)
        .where(
            CompanyPricingPolicy.company_id == company,
        )
        .limit(1)
    )
    if scope is not None:
        # An existing singleton, even an unpublished draft, belongs to its author.
        return ProductDefaultsResult(
            "READY" if scope.latest_revision and pricing_policy else "NEEDS_REVIEW"
        )
    for existing_model in (
        ProductFamily,
        ProductConfigurationScope,
        CompanyProductAuthoringConfiguration,
    ):
        if await db.scalar(
            select(existing_model.id).where(existing_model.company_id == company).limit(1)
        ):
            return ProductDefaultsResult("NEEDS_REVIEW")
    # Avoid introducing a restrictive baseline into an existing pricing setup.
    if pricing_policy is not None:
        return ProductDefaultsResult("NEEDS_REVIEW")
    product_type = await existing_default(db, company, ProductType)
    if product_type is None or not product_type.is_active or product_type.kind != "BOTH":
        return ProductDefaultsResult("NEEDS_REVIEW")
    type_revision = await db.scalar(
        select(ProductTypeRevision)
        .where(
            ProductTypeRevision.company_id == company,
            ProductTypeRevision.product_type_id == product_type.id,
            ProductTypeRevision.published_at.is_not(None),
        )
        .order_by(ProductTypeRevision.revision.desc())
        .limit(1)
    )
    if type_revision is None or any(
        (
            type_revision.require_brand,
            type_revision.require_manufacturer,
            type_revision.require_expiry,
        )
    ):
        return ProductDefaultsResult("NEEDS_REVIEW")
    level = await db.scalar(
        select(PriceLevel).where(
            PriceLevel.company_id == company,
            PriceLevel.ordinal == 1,
            PriceLevel.is_active.is_(True),
        )
    )
    if level is None:
        return ProductDefaultsResult("NEEDS_REVIEW")
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
    sale = await db.scalar(
        select(PricePlan.id)
        .where(
            PricePlan.company_id == company,
            PricePlan.purpose == "SALE",
            PricePlan.price_level_id == level.id,
            PricePlan.currency == profile.base_currency,
        )
        .limit(1)
    )
    if purchase is None or sale is None:
        return ProductDefaultsResult("NEEDS_REVIEW")
    pack = json.loads(
        files("catalog.seeds").joinpath("company_configuration_defaults_v1.json").read_text("utf-8")
    )
    pack["profiles"].update(
        goods_type_revision_mode="VALUE",
        goods_type_revision_id=type_revision.id,
        service_type_revision_mode="VALUE",
        service_type_revision_id=type_revision.id,
    )
    result = ProductDefaultsResult("READY")

    async def create(model: type[Row], **values: Any) -> Row:
        identity = uuid7()
        row = model(id=identity, tenant_id=tenant, company_id=company, **values)
        db.add(row)
        await db.flush()
        entity = "catalog." + row.__tablename__
        action = (
            "publish"
            if model
            in {
                ProductConfigurationRevision,
                CompanyPricingPolicy,
                InventoryProfileTemplateRevision,
                ProductTypeRevision,
            }
            else "create"
        )
        event = audit_event(entity, action)
        payload = audit_payload(
            action=event,
            category=category(entity, action),
            entity_type=entity,
            entity_id=identity,
            actor_user_id=None,
            company_id=company,
            changes=changes(entity, frozenset(values), after=values, creating=True),
            reason=REASON,
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

    if await inventory_enabled(db, company):
        inventory_pack = json.loads(
            files("catalog.seeds").joinpath("simple_inventory_defaults_v1.json").read_text("utf-8")
        )
        if await db.scalar(
            select(ProductType.id).where(
                ProductType.company_id == company,
                ProductType.code == inventory_pack["goods_type"]["code"],
            )
        ) or await db.scalar(
            select(InventoryProfileTemplate.id).where(
                InventoryProfileTemplate.company_id == company,
                InventoryProfileTemplate.code == inventory_pack["template"]["code"],
            )
        ):
            return ProductDefaultsResult("NEEDS_REVIEW")
        template = await create(InventoryProfileTemplate, **inventory_pack["template"])
        inventory_revision = await create(
            InventoryProfileTemplateRevision,
            template_id=template.id,
            revision=1,
            row_version=1,
            published_at=utcnow(),
            **inventory_pack["revision"],
        )
        pack["profiles"].update(
            inventory_template_revision_mode="VALUE",
            inventory_template_revision_id=inventory_revision.id,
        )
        goods_type = await create(ProductType, **inventory_pack["goods_type"])
        goods_revision = await create(
            ProductTypeRevision,
            product_type_id=goods_type.id,
            revision=1,
            row_version=1,
            published_at=utcnow(),
            **inventory_pack["goods_revision"],
        )
        pack["profiles"].update(goods_type_revision_id=goods_revision.id)
    body = CompanyDraftInput(effective_from=BASELINE_DATE, change_reason=REASON, **pack)
    scope = await create(
        ProductConfigurationScope,
        scope_kind="COMPANY",
        owner_id=company,
        row_version=1,
        latest_revision=1,
    )
    draft = await create(
        ProductConfigurationDraft,
        scope_id=scope.id,
        status="PUBLISHED",
        row_version=1,
        effective_from=body.effective_from,
        change_reason=REASON,
    )
    revision = await create(
        ProductConfigurationRevision,
        scope_id=scope.id,
        source_draft_id=draft.id,
        revision=1,
        effective_from=body.effective_from,
        published_at=utcnow(),
        change_reason=REASON,
    )
    for owner, value in (("draft_id", draft.id), ("revision_id", revision.id)):
        for field, model, _ in CHILDREN:
            entries = getattr(body, field)
            for entry in entries if isinstance(entries, list) else [entries]:
                await create(model, **{owner: value}, **entry.model_dump())
    await create(
        CompanyPricingPolicy,
        row_version=1,
        default_level_id=level.id,
        missing_price_policy="ERROR",
        fallback_level_id=None,
        purchase_plan_id=purchase.id,
        sale_unit_mode="EXPLICIT_ONLY",
        purchase_unit_mode="EXPLICIT_ONLY",
        valid_from=BASELINE_DATE,
        valid_to=None,
    )
    if state.generation >= 2**63 - 1:
        raise ConflictError("company policy generation exhausted")
    state.generation += 1
    await db.flush()
    return result
