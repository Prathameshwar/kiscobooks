"""Check required company/unit price definitions without selecting an invoice price."""

import datetime as dt
import uuid
from decimal import Decimal
from fractions import Fraction
from typing import Any, cast

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError
from sqlalchemy import select

from catalog.models import (
    ItemUnitBinding,
    ItemUnitRevision,
    ProductConfigurationRevision,
    ProductTypeRevision,
)
from catalog.models.pricing import (
    CommercialGuardRule,
    CompanyPricingPolicy,
    DiscountCeiling,
    ItemCommercialPolicy,
    ItemMrp,
    ItemPriceFormula,
    ItemPriceNumericRevision,
    ItemPriceSeries,
    ItemPriceTier,
    ItemReferenceCost,
    PriceLevel,
    PricePlan,
    PurchasePriceTerm,
)
from catalog.schemas.pricing import Purpose, ResolveInput
from catalog.tasks.pricing_commands import effective, protected, row
from catalog.tasks.pricing_foundation import level
from catalog.tasks.pricing_publication import draft_input
from catalog.tasks.pricing_readiness import assess
from catalog.tasks.pricing_resolution import in_book
from catalog.tasks.product_attributes import bounded
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import current_rows
from catalog.tasks.tax_resolution import Pins


async def coverage(work: ProductWork, config: Any, as_of: dt.date, pins: Pins) -> list[str]:
    """A draft cannot freeze scheduled unit changes without their required price definitions."""
    assert work.item is not None
    bindings = await bounded(work, ItemUnitBinding, "item_id", work.item.id, 64)
    await protected(work.access, ItemUnitRevision)
    future = list(
        await work.db.scalars(
            select(ItemUnitRevision)
            .where(
                ItemUnitRevision.company_id == work.company,
                ItemUnitRevision.binding_id.in_([binding.id for binding in bindings]),
                ItemUnitRevision.valid_from > as_of,
            )
            .order_by(ItemUnitRevision.valid_from, ItemUnitRevision.id)
            .limit(1025)
        )
    )
    if len(future) > 1024:
        raise ConflictError("scheduled pricing units exceed the review bound")
    dates = {as_of}
    for revision in future:
        await work.access.require(revision)
        pins.add(revision)
        dates.add(revision.valid_from)
    if len(dates) > 64:
        raise ConflictError("scheduled pricing units exceed 64 review dates")
    missing = []
    for date in sorted(dates):
        missing.extend(await coverage_at(work, config, date, pins))
    return sorted(set(missing))


async def coverage_at(work: ProductWork, config: Any, as_of: dt.date, pins: Pins) -> list[str]:
    assert work.item is not None
    access, item = work.access, work.item
    context = await access.context(PricePlan)
    code = context.company.base_currency
    missing = []
    bindings = await bounded(work, ItemUnitBinding, "item_id", item.id, 64)
    revisions = []
    for binding in bindings:
        pins.add(binding)
        for revision in await current_rows(
            work, ItemUnitRevision, "binding_id", binding.id, as_of, limit=2
        ):
            pins.add(revision)
            revisions.append((binding, revision))
    policy = await effective(access, CompanyPricingPolicy, as_of)
    if policy is not None:
        pins.add(policy)
    plans = []
    if item.sellable and config.pricing.sale_price_mode == "REQUIRED":
        if policy is None:
            missing.append("sale_pricing_policy")
        else:
            await protected(access, PriceLevel)
            levels = list(
                await work.db.scalars(
                    select(PriceLevel)
                    .where(
                        PriceLevel.company_id == work.company,
                        PriceLevel.ordinal <= config.pricing.sale_level_count,
                    )
                    .limit(65)
                )
            )
            wanted = {entry.id for entry in levels} | {policy.default_level_id}
            if len(levels) < config.pricing.sale_level_count:
                missing.append("required_sale_levels")
            for level_id in wanted:
                selected = await level(access, level_id)
                pins.add(selected)
                plan = await work.db.scalar(
                    select(PricePlan).where(
                        PricePlan.company_id == work.company,
                        PricePlan.price_level_id == selected.id,
                        PricePlan.currency == code,
                    )
                )
                if plan is None:
                    missing.append("sale_book:" + str(selected.id))
                else:
                    await access.require(plan)
                    plans.append(plan)
    if item.purchasable and config.pricing.purchase_reference_mode == "REQUIRED":
        work.actor.require_scope("purchase_price.read", target=ScopePath(company_id=work.company))
        if policy is None or policy.purchase_plan_id is None:
            missing.append("purchase_pricing_policy")
        else:
            plan = await row(access, PricePlan, policy.purchase_plan_id)
            if plan.purpose != "PURCHASE" or plan.currency != code:
                missing.append("purchase_book")
            else:
                plans.append(plan)
    missing_mrp: set[uuid.UUID] = set()
    if config.pricing.mrp_mode == "REQUIRED":
        if work.family.kind != "GOODS":
            raise ConflictError("service products cannot require MRP")
        for binding, revision in revisions:
            if binding.usage_role == "PURCHASE":
                continue
            mrp = await effective(
                access,
                ItemMrp,
                as_of,
                item_id=item.id,
                unit_revision_id=revision.id,
                currency=code,
                jurisdiction=context.company.country_code,
            )
            if mrp is None:
                missing_mrp.add(revision.id)
                missing.append("mrp:" + str(revision.id))
            else:
                pins.add(mrp)
    for plan in plans:
        assert policy is not None
        pins.add(plan)
        mode = policy.purchase_unit_mode if plan.purpose == "PURCHASE" else policy.sale_unit_mode
        for binding, revision in revisions:
            if (plan.purpose == "SALE" and binding.usage_role == "PURCHASE") or (
                plan.purpose == "PURCHASE" and binding.usage_role == "SALE"
            ):
                continue
            quantity = revision.quantity_increment or Decimal(1)
            if not revision.fractional_entry and quantity < 1:
                quantity = Decimal(1)
            query = ResolveInput(
                item_id=item.id,
                unit_revision_id=revision.id,
                currency=code,
                as_of=as_of,
                purpose=cast(Purpose, plan.purpose),
                quantity=quantity,
            )
            price, pricing_revision, pricing_quantity, _ = await in_book(
                access, plan, query, revision, mode
            )
            if price is None:
                missing.append("price:" + str(plan.id) + ":" + str(revision.id))
                continue
            pins.add(price)
            if plan.purpose == "SALE" and revision.id in missing_mrp:
                # Already ineligible: report the missing declaration before assessing its price.
                continue
            ends = [
                date
                for date in (price.valid_to, revision.valid_to, pricing_revision.valid_to)
                if date is not None
            ]
            definition = (await draft_input(access, price)).model_copy(
                update={
                    "valid_from": as_of,
                    "valid_to": min(ends) if ends else None,
                }
            )
            assessment = await assess(
                access,
                definition,
                entering=False,
                requested_revision=revision.id,
                unit_factor=Fraction(pricing_quantity) / Fraction(quantity),
                check_schedule=True,
            )
            source_ids = assessment.source_ids
            missing.extend(
                "price_guard:" + str(plan.id) + ":" + str(revision.id) + ":" + issue.code
                for issue in assessment.issues
            )
            for model in (
                ItemPriceSeries,
                ItemPriceNumericRevision,
                ProductConfigurationRevision,
                ProductTypeRevision,
                ItemCommercialPolicy,
                ItemReferenceCost,
                ItemMrp,
                CommercialGuardRule,
                DiscountCeiling,
                ItemUnitRevision,
            ):
                for source in await work.db.scalars(
                    select(model).where(model.company_id == work.company, model.id.in_(source_ids))
                ):
                    await access.require(source)
                    pins.add(source)
            for child in (ItemPriceTier, ItemPriceFormula, PurchasePriceTerm):
                if child is PurchasePriceTerm and plan.purpose != "PURCHASE":
                    continue
                rows = list(
                    await work.db.scalars(
                        select(child)
                        .where(child.company_id == work.company, child.price_id == price.id)
                        .limit(65)
                    )
                )
                # draft_input already validated the complete aggregate's bounds.
                for source in rows:
                    await access.require(source)
                    pins.add(source)
    return missing
