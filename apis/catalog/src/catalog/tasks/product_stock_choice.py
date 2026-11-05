"""Validate an explicit batch selection against native company/type/profile rules."""

import datetime as dt
from typing import Any

from billing_platform.errors import ValidationFailedError
from sqlalchemy import select

from catalog.models.commercial import ProductTypeRevision
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.product_stock_choice import ItemStockChoice
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import protected
from catalog.tasks.product_commands import ProductWork


async def available(
    access: ConfigurationAccess, config: EffectiveConfiguration, type_id: Any, kind: str
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "required": False,
        "expiry_enabled": False,
        "expiry_required": False,
        "manufacture_date_required": False,
    }
    if kind != "GOODS" or config.profiles.inventory_template_revision_id is None or type_id is None:
        return result
    template = await access.reference(
        InventoryProfileTemplateRevision, config.profiles.inventory_template_revision_id
    )
    product_type = await access.reference(ProductTypeRevision, type_id)
    context = await access.context(InventoryProfileTemplateRevision)
    enabled = (
        {"inventory", "batch_tracking"} <= context.features
        and template.lot_tracking
        and ("BATCH_SERIAL" if template.serial_tracking else "BATCH") in product_type.tracking_modes
        and (not template.serial_tracking or "serial_tracking" in context.features)
    )
    return result | {
        "available": enabled,
        "required": enabled
        and (
            template.serial_tracking
            or "NONE" not in product_type.tracking_modes
            or product_type.require_expiry
        ),
        "expiry_enabled": enabled and "expiry_tracking" in context.features,
        "expiry_required": enabled and template.expiry_required,
        "manufacture_date_required": enabled and template.manufacture_date_required,
    }


async def selection(access: ConfigurationAccess, item_id: Any) -> ItemStockChoice | None:
    await protected(access, ItemStockChoice)
    selected = await access.db.scalar(
        select(ItemStockChoice).where(
            ItemStockChoice.company_id == access.company, ItemStockChoice.item_id == item_id
        )
    )
    if selected is not None:
        await access.require(selected)
    return selected


async def validate(work: ProductWork, config: EffectiveConfiguration, batch_enabled: bool) -> None:
    options = await available(
        work.access, config, work.family.product_type_revision_id, work.family.kind
    )
    if not options["available"] or (options["required"] and not batch_enabled):
        raise ValidationFailedError(
            "Batch selection is not allowed by the product configuration",
            fields={"batch_enabled": "Review the Goods type and inventory profile"},
        )


async def capture(work: ProductWork, batch_enabled: bool, as_of: dt.date) -> None:
    from catalog.tasks.product_requirements import configuration

    assert work.item is not None
    await validate(work, await configuration(work, as_of, proposed=True), batch_enabled)
    work.db.add(await work.new(ItemStockChoice, item_id=work.item.id, batch_enabled=batch_enabled))


def profile_values(
    template: InventoryProfileTemplateRevision, choice: ItemStockChoice | None
) -> dict[str, Any]:
    values = {
        key: getattr(template, key)
        for key in (
            "identifier_profile_id",
            "lot_tracking",
            "serial_tracking",
            "expiry_required",
            "manufacture_date_required",
            "shelf_life_days",
            "minimum_remaining_life_days",
            "issue_strategy",
            "valuation_method",
            "negative_stock_policy",
        )
    }
    if choice is not None and not choice.batch_enabled:
        values.update(
            lot_tracking=False,
            expiry_required=False,
            manufacture_date_required=False,
            shelf_life_days=None,
            minimum_remaining_life_days=None,
            issue_strategy="FIFO",
        )
    return values
