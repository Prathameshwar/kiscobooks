"""Validate price sources and exact entry against the selected product configuration."""

import datetime as dt
from decimal import Decimal
from fractions import Fraction
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError

from catalog.domain.pricing import RateGrid, Tier, purchase_net, recipe_rate, validate_tiers
from catalog.models.pricing import (
    ItemCommercialPolicy,
    ItemMrp,
    ItemPriceScope,
    ItemPriceSeries,
    ItemReferenceCost,
    PricePlan,
)
from catalog.schemas.pricing import DraftInput, FormulaInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import effective, product, purpose_access, row
from catalog.tasks.pricing_dimensions import validate_dimensions
from catalog.tasks.pricing_foundation import basis, currency, level, numeric, unit
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import configuration
from catalog.tasks.product_unit_rules import require_serial_base


async def settings(
    access: ConfigurationAccess, item_id: Any, as_of: dt.date
) -> tuple[Any, Any, Any]:
    item, family = await product(access, item_id)
    if item.status == "DISCONTINUED" or family.status == "DISCONTINUED":
        raise ConflictError("new pricing requires a current product")
    work = ProductWork(access.db, access.actor, access.company, family, item, access)
    config = await configuration(work, as_of)
    await require_serial_base(work, config, as_of)
    if family.kind == "SERVICE" and config.pricing.mrp_mode == "REQUIRED":
        raise ConflictError("services cannot require a product MRP declaration")
    return item, family, config


async def source_rate(
    access: ConfigurationAccess,
    formula: FormulaInput,
    item_id: Any,
    revision_id: Any,
    code: str,
    as_of: dt.date,
    tax_basis: str,
    *,
    batch_scope: ItemPriceScope | None = None,
) -> tuple[Fraction, Any]:
    if formula.recipe == "MRP_LESS_PERCENT" and batch_scope is not None:
        context = await access.context(ItemPriceScope)
        if formula.jurisdiction != context.company.country_code:
            raise ConflictError("Batch MRP requires its company declaration jurisdiction")
        _, binding = await unit(access, item_id, revision_id, as_of)
        if batch_scope.lot_mrp is None:
            raise ConflictError("The batch's physical MRP declaration is required")
        if (batch_scope.item_id, batch_scope.lot_currency, batch_scope.lot_unit_id) != (
            item_id,
            code,
            binding.unit_id,
        ):
            raise ConflictError("Batch MRP applies only to its declared unit and currency")
        if tax_basis != "INCLUSIVE":
            raise ConflictError("formula requires unavailable transaction tax-basis context")
        return recipe_rate(
            Fraction(batch_scope.lot_mrp), formula.recipe, formula.percentage
        ), batch_scope.id
    source: ItemMrp | ItemReferenceCost | None
    if formula.recipe == "MRP_LESS_PERCENT":
        source = await effective(
            access,
            ItemMrp,
            as_of,
            item_id=item_id,
            unit_revision_id=revision_id,
            currency=code,
            jurisdiction=formula.jurisdiction,
        )
    else:
        source = await effective(
            access,
            ItemReferenceCost,
            as_of,
            item_id=item_id,
            unit_revision_id=revision_id,
            currency=code,
            estimate_kind=formula.estimate_kind,
        )
    if source is None:
        raise ConflictError("formula requires an effective authoritative reference source")
    if source.tax_basis != tax_basis:
        raise ConflictError("formula requires unavailable transaction tax-basis context")
    return recipe_rate(
        Fraction(source.amount) / Fraction(source.price_basis_quantity),
        formula.recipe,
        formula.percentage,
    ), source.id


async def validate(
    access: ConfigurationAccess, body: DraftInput, *, entering: bool = True
) -> tuple[ItemPriceSeries, PricePlan, RateGrid, Decimal | None, list[Any]]:
    series = await row(access, ItemPriceSeries, body.series_id)
    plan = await row(access, PricePlan, series.plan_id)
    await purpose_access(access, plan)
    await currency(access, series.currency)
    selected_level = (
        await level(access, plan.price_level_id) if plan.price_level_id is not None else None
    )
    item, family, config = await settings(access, series.item_id, body.valid_from)
    if plan.purpose == "PURCHASE":
        if not item.purchasable or config.pricing.purchase_reference_mode == "DISABLED":
            raise ConflictError("purchase-reference pricing is disabled for this SKU")
    elif not item.sellable or config.pricing.sale_price_mode == "DISABLED":
        raise ConflictError("sale/reference-retail pricing is disabled for this SKU")
    revision, binding = await unit(
        access, item.id, series.unit_revision_id, body.valid_from, purpose=plan.purpose
    )
    await validate_dimensions(
        access,
        config,
        base_unit_id=item.base_unit_id,
        unit_id=binding.unit_id,
        currency=series.currency,
        channel_code=series.channel_code,
        price_method=body.price_method,
        price_level_ordinal=selected_level.ordinal if selected_level else 1,
    )
    basis(revision, body.price_basis_quantity)
    precision = await numeric(
        access,
        body.numeric_revision_id,
        item.id,
        revision.id,
        series.currency,
        body.valid_from,
        entering=entering,
    )
    grid = RateGrid(precision.price_decimal_places, precision.price_increment)
    commercial = await effective(access, ItemCommercialPolicy, body.valid_from, item_id=item.id)
    free = plan.purpose == "SALE" and commercial is not None and commercial.free_sale_allowed
    amount = body.amount
    source_ids = [
        series.id,
        plan.id,
        precision.id,
        revision.id,
        item.id,
        family.id,
        family.product_type_revision_id,
        *(source.revision_id for source in config.sources),
    ]
    if commercial is not None:
        source_ids.append(commercial.id)
    if body.price_method == "FIXED":
        assert amount is not None
        grid.entered(amount, free=free)
    elif body.price_method == "TIERS":
        tiers = tuple(Tier(t.min_quantity, t.max_quantity, t.amount) for t in body.tiers)
        validate_tiers(tiers, grid, free=free)
        for tier in tiers:
            basis(revision, tier.minimum)
            if tier.maximum is not None:
                basis(revision, tier.maximum)
    else:
        assert body.formula is not None
        if plan.purpose != "SALE":
            raise ValidationFailedError("native price recipes require a SALE book")
        scope = await row(access, ItemPriceScope, series.price_scope_id)
        rate, source_id = await source_rate(
            access,
            body.formula,
            item.id,
            revision.id,
            series.currency,
            body.valid_from,
            plan.tax_basis,
            batch_scope=scope if scope.lot_id is not None else None,
        )
        amount = grid.rounded(
            rate * Fraction(body.price_basis_quantity), body.formula.rounding_mode
        )
        grid.entered(amount, free=free)
        source_ids.append(source_id)
    if body.purchase_term is not None:
        if plan.purpose != "PURCHASE":
            raise ValidationFailedError("purchase quote terms require a PURCHASE book")
        term = body.purchase_term
        grid.entered(term.gross_amount)
        if term.discount_kind == "FIXED_PER_BASIS":
            grid.entered(term.discount_value, free=True)
        if purchase_net(term.gross_amount, term.discount_kind, term.discount_value) != amount:
            raise ValidationFailedError(
                "gross quote and discount do not reconcile to the net price"
            )
    return series, plan, grid, amount, source_ids
