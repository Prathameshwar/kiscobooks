"""Batch references and native rates. Physical declarations belong to Accounting."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import select

from catalog.models.pricing import (
    CompanyPricingPolicy,
    ItemPriceNumericRevision,
    ItemPriceScope,
    PricePlan,
    PricingRow,
)
from catalog.schemas import pricing as p
from catalog.schemas.batch_pricing import BatchPricingInput
from catalog.schemas.simple_product_creation import SimpleBatchInput, SimpleSalePrice
from catalog.tasks import pricing_foundation as foundation
from catalog.tasks import pricing_publication as publication
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import PricingWork, effective, protected, row
from catalog.tasks.pricing_validation import settings
from catalog.tasks.product_stock_choice import selection
from catalog.tasks.simple_sale_prices import sale_amounts


async def batch_scope(
    access: ConfigurationAccess, item_id: uuid.UUID, lot_id: uuid.UUID
) -> ItemPriceScope:
    await protected(access, ItemPriceScope)
    found = await access.db.scalar(
        select(ItemPriceScope).where(
            ItemPriceScope.company_id == access.company,
            ItemPriceScope.item_id == item_id,
            ItemPriceScope.lot_id == lot_id,
        )
    )
    if found is None:
        raise PermissionDeniedError("Batch pricing reference is unavailable for this product")
    await access.require(found)
    return found


async def publish_initial(
    work: PricingWork, body: BatchPricingInput, verified: dict[str, Any]
) -> PricingRow:
    await work.publication(body)
    item, family, config = await settings(work.access, body.item_id, body.valid_from)
    choice = await selection(work.access, item.id)
    if family.kind != "GOODS" or choice is None or not choice.batch_enabled:
        raise ConflictError("This product does not use batch prices")
    policy = await effective(work.access, CompanyPricingPolicy, body.valid_from)
    if policy is None:
        raise ConflictError("Complete company pricing defaults")
    sales = []
    purchase = None
    base_currency = (await work.access.context(PricePlan)).company.base_currency
    for entry in body.prices:
        plan = await row(work.access, PricePlan, entry.plan_id)
        if plan.currency != base_currency:
            raise ValidationFailedError("Initial batch prices use company currency")
        if plan.purpose == "SALE" and plan.price_level_id is not None:
            sales.append(SimpleSalePrice(price_level_id=plan.price_level_id, amount=entry.amount))
        elif plan.purpose == "PURCHASE" and plan.id == policy.purchase_plan_id:
            purchase = entry.amount
        else:
            raise ValidationFailedError("Choose configured sale or purchase price books")
    from catalog.tasks.simple_sale_prices import multiple_enabled

    multiple = await multiple_enabled(work.access, config)
    if not multiple and any(entry.price_level_id != policy.default_level_id for entry in sales):
        raise ValidationFailedError("Multiple selling-price levels are disabled")
    await sale_amounts(
        work.access,
        config,
        body.valid_from,
        SimpleBatchInput(
            code="validation",
            sale_prices=sales if multiple else [],
            sale_price=sales[0].amount if sales and not multiple else None,
        ),
    )
    if config.pricing.purchase_reference_mode == "REQUIRED" and purchase is None:
        raise ValidationFailedError("Batch purchase price is required")
    if (
        verified.get("id"),
        verified.get("company_id"),
        verified.get("item_id"),
        verified.get("status"),
        verified.get("is_held"),
    ) != (str(body.lot_id), str(work.company), str(item.id), "ACTIVE", False):
        raise PermissionDeniedError("An active batch of this company and product is required")
    if not {"mrp_amount", "mrp_currency", "mrp_unit_id"} <= verified.keys():
        raise PermissionDeniedError("The batch's physical declaration fields are protected")
    mrp = Decimal(verified["mrp_amount"]) if verified["mrp_amount"] is not None else None
    if config.pricing.mrp_mode == "REQUIRED" and mrp is None:
        raise ValidationFailedError("Batch MRP is required")
    if config.pricing.mrp_mode == "DISABLED" and mrp is not None:
        raise ValidationFailedError("Batch MRP is disabled by Product Configuration")
    if mrp is not None and (verified["mrp_currency"], verified["mrp_unit_id"]) != (
        (await work.access.context(PricePlan)).company.base_currency,
        str(item.base_unit_id),
    ):
        raise ConflictError("Batch MRP requires its verified base unit and company currency")
    await protected(work.access, ItemPriceScope)
    if await work.db.scalar(
        select(ItemPriceScope.id).where(
            ItemPriceScope.company_id == work.company,
            ItemPriceScope.item_id == item.id,
            ItemPriceScope.lot_id == body.lot_id,
        )
    ):
        raise ConflictError("Batch prices already exist; replay the original request")
    scope = await work.new(
        ItemPriceScope,
        item_id=item.id,
        subject_kind="LOT",
        lot_id=body.lot_id,
        lot_mrp=mrp,
        lot_currency=verified["mrp_currency"],
        lot_unit_id=uuid.UUID(verified["mrp_unit_id"]) if mrp is not None else None,
    )
    if len({entry.plan_id for entry in body.prices}) != len(body.prices):
        raise ValidationFailedError("Batch price books must be distinct")
    for entry in body.prices:
        plan = await row(work.access, PricePlan, entry.plan_id)
        numeric: PricingRow | None = await effective(
            work.access,
            ItemPriceNumericRevision,
            body.valid_from,
            item_id=item.id,
            unit_revision_id=body.unit_revision_id,
            currency=plan.currency,
        )
        if numeric is None:
            numeric = await foundation.create_numeric(
                work,
                p.NumericInput(
                    expected_generation=body.expected_generation,
                    expected_source_version=body.expected_source_version,
                    item_id=item.id,
                    unit_revision_id=body.unit_revision_id,
                    currency=plan.currency,
                    valid_from=body.valid_from,
                    price_decimal_places=entry.price_decimal_places,
                ),
                None,
            )
        series = await foundation.create_series(
            work,
            p.SeriesInput(
                plan_id=plan.id, price_scope_id=scope.id, unit_revision_id=body.unit_revision_id
            ),
            None,
        )
        draft = await publication.save_draft(
            work,
            p.DraftInput(
                series_id=series.id,
                numeric_revision_id=numeric.id,
                valid_from=body.valid_from,
                price_method="FIXED",
                amount=entry.amount,
                price_basis_quantity=entry.price_basis_quantity,
            ),
            None,
        )
        await publication.publish(
            work,
            p.PublishInput(
                expected_version=draft.row_version,
                expected_generation=body.expected_generation,
                expected_source_version=body.expected_source_version,
            ),
            draft.id,
        )
    return scope
