"""Dated regular-price resolution, with explicit absence and authorized level selection."""

import uuid
from decimal import Decimal
from fractions import Fraction
from typing import Any, cast

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.pricing import Tier, select_tier, storage
from catalog.models.pricing import (
    CompanyPricingPolicy,
    ItemPrice,
    ItemPriceScope,
    ItemPriceSeries,
    ItemPriceTier,
    PricePlan,
)
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.sales_channel import SalesChannel
from catalog.schemas.pricing import ExactRatio, PriceResolution, ResolveInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.customer_pricing import customer_pricing_choice
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import effective, protected, purpose_access, row
from catalog.tasks.pricing_foundation import basis, currency, level, unit
from catalog.tasks.pricing_guards import GuardResult, restrictions
from catalog.tasks.pricing_publication import draft_input
from catalog.tasks.pricing_readiness import MESSAGES
from catalog.tasks.pricing_validation import settings, validate
from catalog.tasks.product_commands import ProductWork


def ratio(value: Fraction | None) -> ExactRatio | None:
    return (
        ExactRatio(numerator=str(value.numerator), denominator=str(value.denominator))
        if value is not None
        else None
    )


async def select_plan(
    access: ConfigurationAccess,
    query: ResolveInput,
    policy: CompanyPricingPolicy,
    selected_level_id: uuid.UUID,
) -> PricePlan | None:
    await protected(access, PricePlan)
    override = query.price_level_id is not None or (
        query.plan_id is not None and query.purpose != "REFERENCE_RETAIL"
    )
    if override:
        access.actor.require_scope(
            "price_plan.override", target=ScopePath(company_id=access.company)
        )
        if query.override_reason is None:
            raise ValidationFailedError("administrative price selection requires a reason")
    elif query.override_reason is not None:
        raise ValidationFailedError("override reason requires an explicit administrative selection")
    if query.price_level_id is not None and query.purpose != "SALE":
        raise ValidationFailedError("only sale resolution accepts a price level")
    plan: PricePlan | None
    if query.plan_id is not None:
        plan = await row(access, PricePlan, query.plan_id)
        await purpose_access(access, plan)
        if plan.purpose != query.purpose or plan.currency != query.currency:
            raise ValidationFailedError("selected book does not match purpose/currency")
        if query.price_level_id is not None and plan.price_level_id != query.price_level_id:
            raise ValidationFailedError("selected book and price level disagree")
    elif query.purpose == "SALE":
        chosen = await level(access, query.price_level_id or selected_level_id)
        plan = await access.db.scalar(
            select(PricePlan).where(
                PricePlan.company_id == access.company,
                PricePlan.price_level_id == chosen.id,
                PricePlan.currency == query.currency,
            )
        )
    elif query.purpose == "PURCHASE":
        if policy.purchase_plan_id is None:
            return None
        plan = await row(access, PricePlan, policy.purchase_plan_id)
        if plan.purpose != "PURCHASE" or plan.currency != query.currency:
            return None
    else:
        raise ValidationFailedError("reference retail resolution requires an explicit book")
    if plan is not None:
        await access.require(plan)
        await purpose_access(access, plan)
        if plan.price_level_id is not None:
            await level(access, plan.price_level_id)
    return plan


async def candidate(
    access: ConfigurationAccess,
    plan: PricePlan,
    item_id: uuid.UUID,
    revision_id: uuid.UUID,
    as_of: Any,
    channel_code: str | None,
    lot_id: uuid.UUID | None = None,
) -> ItemPrice | None:
    await protected(access, ItemPriceSeries)
    await protected(access, ItemPriceScope)
    for code in (channel_code, None) if channel_code is not None else (None,):
        series = await access.db.scalar(
            select(ItemPriceSeries)
            .join(ItemPriceScope, ItemPriceScope.id == ItemPriceSeries.price_scope_id)
            .where(
                ItemPriceSeries.company_id == access.company,
                ItemPriceSeries.item_id == item_id,
                ItemPriceSeries.plan_id == plan.id,
                ItemPriceSeries.unit_revision_id == revision_id,
                ItemPriceSeries.channel_code == code,
                ItemPriceScope.lot_id == lot_id,
            )
        )
        if series is None:
            continue
        await access.require(series)
        price = cast(
            ItemPrice | None, await effective(access, ItemPrice, as_of, series_id=series.id)
        )
        if price is not None:
            return price
    return None


async def base_revision(access: ConfigurationAccess, query: ResolveInput) -> ItemUnitRevision:
    await protected(access, ItemUnitBinding)
    await protected(access, ItemUnitRevision)
    rows = list(
        await access.db.scalars(
            select(ItemUnitRevision)
            .join(
                ItemUnitBinding,
                (ItemUnitBinding.tenant_id == ItemUnitRevision.tenant_id)
                & (ItemUnitBinding.company_id == ItemUnitRevision.company_id)
                & (ItemUnitBinding.id == ItemUnitRevision.binding_id),
            )
            .where(
                ItemUnitRevision.company_id == access.company,
                ItemUnitBinding.item_id == query.item_id,
                ItemUnitBinding.usage_role == "BASE",
                ItemUnitRevision.valid_from <= query.as_of,
                or_(ItemUnitRevision.valid_to.is_(None), ItemUnitRevision.valid_to >= query.as_of),
            )
            .limit(2)
        )
    )
    if len(rows) != 1:
        raise ConflictError("base price derivation requires one effective base revision")
    await access.require(rows[0])
    return rows[0]


async def in_book(
    access: ConfigurationAccess,
    plan: PricePlan,
    query: ResolveInput,
    requested: ItemUnitRevision,
    mode: str,
) -> tuple[ItemPrice | None, ItemUnitRevision, Decimal, bool]:
    price = await candidate(
        access, plan, query.item_id, requested.id, query.as_of, query.channel_code, query.lot_id
    )
    if price is None and mode == "EXACT_BASE_DERIVATION":
        base = await base_revision(access, query)
        if requested.id != base.id:
            price = await candidate(
                access, plan, query.item_id, base.id, query.as_of, query.channel_code, query.lot_id
            )
            if price is not None:
                if requested.conversion_mode != "FIXED":
                    raise ConflictError("base price derivation requires actual measured quantity")
                assert requested.numerator is not None and requested.denominator is not None
                quantity = storage(
                    Fraction(query.quantity) * Fraction(requested.numerator, requested.denominator)
                )
                basis(base, quantity)
                return price, base, quantity, True
    return price, requested, query.quantity, False


async def resolve(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: ResolveInput,
    *,
    coverage: bool = False,
) -> PriceResolution:
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(PricePlan)
    if query.party_id is not None and query.purpose != "SALE":
        raise ValidationFailedError("buyer-specific price selection is only supported for sales")
    if query.purpose == "PURCHASE":
        actor.require_scope("purchase_price.read", target=ScopePath(company_id=company))
    if query.channel_code is not None:
        if query.purpose != "SALE":
            raise ValidationFailedError("only sale prices may name a sales channel")
        await protected(access, SalesChannel)
        channel = await db.scalar(
            select(SalesChannel).where(
                SalesChannel.company_id == company,
                SalesChannel.code == query.channel_code,
            )
        )
        if channel is None or not channel.is_active:
            raise ValidationFailedError("sales channel is unavailable")
        await access.require(channel)
    await currency(access, query.currency)
    item, family, config = await settings(access, query.item_id, query.as_of)
    from catalog.tasks.batch_pricing import batch_scope
    from catalog.tasks.product_stock_choice import selection

    choice = await selection(access, item.id)
    if choice is not None and choice.batch_enabled and query.lot_id is None:
        raise ValidationFailedError(
            "Choose a batch to resolve this product's price", fields={"lot_id": "Batch is required"}
        )
    selected_scope = (
        await batch_scope(access, item.id, query.lot_id) if query.lot_id is not None else None
    )
    # A disabled channel/currency must not silently fall back to an unrelated price.
    from catalog.tasks.pricing_dimensions import validate_dimensions

    await validate_dimensions(
        access,
        config,
        base_unit_id=item.base_unit_id,
        unit_id=item.base_unit_id,
        currency=query.currency,
        channel_code=query.channel_code,
    )
    if query.purpose == "PURCHASE":
        if not item.purchasable or config.pricing.purchase_reference_mode == "DISABLED":
            raise ConflictError("purchase references are disabled for this SKU")
    elif not item.sellable or config.pricing.sale_price_mode == "DISABLED":
        raise ConflictError("sale prices are disabled for this SKU")
    requested, _ = await unit(
        access, query.item_id, query.unit_revision_id, query.as_of, purpose=query.purpose
    )
    basis(requested, query.quantity)
    if (
        item.min_sale_quantity is not None
        and query.purpose == "SALE"
        and requested.conversion_mode == "FIXED"
    ):
        assert requested.numerator is not None and requested.denominator is not None
        if Fraction(query.quantity) * Fraction(
            requested.numerator, requested.denominator
        ) < Fraction(item.min_sale_quantity):
            raise ValidationFailedError("billed quantity is below the minimum sale quantity")
    state = await policy_state(db, actor, company)
    result = PriceResolution(
        status="MISSING",
        item_id=item.id,
        lot_id=query.lot_id,
        as_of=query.as_of,
        purpose=query.purpose,
        currency=query.currency,
        requested_unit_revision_id=requested.id,
        quantity=query.quantity,
        requested_channel_code=query.channel_code,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
    )
    policy = await effective(access, CompanyPricingPolicy, query.as_of)
    if policy is None:
        if coverage:
            return result
        raise ConflictError("company pricing policy is missing")
    selected_level_id = policy.default_level_id
    if query.party_id is not None:
        actor.require_scope("customer_pricing.read", target=ScopePath(company_id=company))
        await protected(access, PricePlan)
        buyer = await customer_pricing_choice(
            db,
            company,
            party_id=query.party_id,
            as_of=query.as_of,
            default_level_id=policy.default_level_id,
        )
        await level(access, buyer.price_level_id)
        selected_level_id = buyer.price_level_id
        result.buyer_party_id = query.party_id
        result.buyer_price_level_id = buyer.price_level_id
        result.buyer_pricing_chain = buyer.chain
        result.source_ids.extend(buyer.source_ids)
    plan = await select_plan(access, query, policy, selected_level_id)
    price = None
    pricing_revision = requested
    pricing_quantity = query.quantity
    mode = policy.purchase_unit_mode if query.purpose == "PURCHASE" else policy.sale_unit_mode
    if plan is not None:
        price, pricing_revision, pricing_quantity, result.unit_derivation_used = await in_book(
            access, plan, query, requested, mode
        )
    # Fallback is only for absent coverage. Errors from denied, stale or invalid sources propagate.
    if (
        price is None
        and query.purpose == "SALE"
        and query.plan_id is None
        and query.price_level_id is None
        and policy.missing_price_policy == "FALLBACK"
    ):
        assert policy.fallback_level_id is not None
        await level(access, policy.fallback_level_id)
        fallback = await access.db.scalar(
            select(PricePlan).where(
                PricePlan.company_id == company,
                PricePlan.price_level_id == policy.fallback_level_id,
                PricePlan.currency == query.currency,
            )
        )
        if fallback is not None:
            price, pricing_revision, pricing_quantity, result.unit_derivation_used = await in_book(
                access, fallback, query, requested, mode
            )
            if price is not None:
                plan = fallback
                result.fallback_used = True
    if price is None or plan is None:
        if coverage:
            return result
        raise ConflictError("regular price coverage is missing")
    definition = await draft_input(access, price)
    current_definition = definition.model_copy(update={"valid_from": query.as_of})
    _, _, _, amount, sources = await validate(access, current_definition, entering=False)
    if definition.price_method == "TIERS":
        index = select_tier(
            tuple(Tier(t.min_quantity, t.max_quantity, t.amount) for t in definition.tiers),
            pricing_quantity,
        )
        amount = definition.tiers[index].amount
        tier = await db.scalar(
            select(ItemPriceTier).where(
                ItemPriceTier.company_id == company,
                ItemPriceTier.price_id == price.id,
                ItemPriceTier.min_quantity == definition.tiers[index].min_quantity,
            )
        )
        assert tier is not None
        result.tier_id = tier.id
    assert amount is not None
    work = ProductWork(db, actor, company, family, item, access)
    guards = GuardResult()
    if query.purpose == "SALE":
        guards = await restrictions(
            access,
            work,
            requested.id,
            query.currency,
            query.as_of,
            plan.tax_basis,
            query.jurisdiction or context.company.country_code,
            mrp_required=config.pricing.mrp_mode == "REQUIRED",
            batch_scope=selected_scope,
        )
    regular = (
        Fraction(amount)
        / Fraction(definition.price_basis_quantity)
        * Fraction(pricing_quantity)
        / Fraction(query.quantity)
    )
    violations = guards.violations(regular)
    if violations:
        raise ConflictError(MESSAGES[violations[0]])
    result.status = "NEEDS_TAX_CONTEXT" if guards.needs_tax else "RESOLVED"
    result.plan_id, result.price_level_id, result.series_id, result.price_id = (
        plan.id,
        plan.price_level_id,
        price.series_id,
        price.id,
    )
    selected_series = await row(access, ItemPriceSeries, price.series_id)
    result.selected_channel_code = selected_series.channel_code
    result.pricing_unit_revision_id, result.numeric_revision_id = (
        pricing_revision.id,
        price.numeric_revision_id,
    )
    result.tax_basis, result.price_basis_quantity = plan.tax_basis, definition.price_basis_quantity
    result.source_ids = list(
        dict.fromkeys([policy.id, price.id, *result.source_ids, *sources, *guards.source_ids])
    )
    result.minimum_rate, result.maximum_rate = ratio(guards.minimum), ratio(guards.maximum)
    result.max_discount_pct = guards.max_discount_pct
    result.guard_ids, result.approval_guard_ids = list(guards.guard_ids), list(guards.approval_ids)
    result.purchase_term = definition.purchase_term
    if not guards.needs_tax:
        result.amount = amount
        result.exact_consideration = ratio(
            Fraction(amount)
            * Fraction(pricing_quantity)
            / Fraction(definition.price_basis_quantity)
        )
    return result
