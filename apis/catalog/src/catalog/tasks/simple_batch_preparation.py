"""Validate batch rows before creating any native product or stock identity."""

import datetime as dt
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError
from billing_platform.money import MoneyError

from catalog.domain.pricing import RateGrid
from catalog.domain.units import QuantityRule
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.pricing import CompanyPricingPolicy, PricePlan
from catalog.schemas.configuration import AuthoringDefaults
from catalog.schemas.product_initial import InitialPrice
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import effective
from catalog.tasks.product_stock_choice import available
from catalog.tasks.simple_sale_prices import sale_amounts


async def prepare_batches(
    access: ConfigurationAccess,
    defaults: AuthoringDefaults,
    body: SimpleCreationInput,
    today: dt.date,
    opening_date: dt.date,
) -> list[dict[str, Any]]:
    config = defaults.configuration
    options = await available(access, config, defaults.product_type_revision_id, body.kind)
    if body.batch_enabled is None:
        if options["available"]:
            raise ValidationFailedError(
                "Choose whether this product uses batches",
                fields={"batch_enabled": "Select Allow batch or leave it off explicitly"},
            )
        return []
    if not options["available"] or (options["required"] and not body.batch_enabled):
        raise ValidationFailedError(
            "Batch selection is not allowed by current configuration",
            fields={"batch_enabled": "Review the Goods type and inventory profile"},
        )
    if not body.batch_enabled:
        return []
    assert defaults.quantity is not None and defaults.price is not None
    assert config.profiles.inventory_template_revision_id is not None
    template = await access.reference(
        InventoryProfileTemplateRevision, config.profiles.inventory_template_revision_id
    )
    policy = await effective(access, CompanyPricingPolicy, today)
    result = []
    for index, entry in enumerate(body.batches):
        prefix = f"batches.{index}."
        try:
            if options["expiry_required"] and entry.expires_on is None:
                raise ValidationFailedError(
                    "Enter expiry", fields={"expires_on": "Required by Product Configuration"}
                )
            if entry.expires_on is not None and not options["expiry_enabled"]:
                raise ValidationFailedError(
                    "Expiry is disabled", fields={"expires_on": "Enable expiry tracking"}
                )
            if options["manufacture_date_required"] and entry.manufactured_on is None:
                raise ValidationFailedError(
                    "Enter manufacture date",
                    fields={"manufactured_on": "Required by the inventory profile"},
                )
            if (
                entry.manufactured_on
                and entry.expires_on
                and template.shelf_life_days is not None
                and (entry.expires_on - entry.manufactured_on).days > template.shelf_life_days
            ):
                raise ValidationFailedError(
                    "Expiry exceeds shelf life",
                    fields={"expires_on": "Review the configured shelf life"},
                )
            if entry.opening_quantity:
                QuantityRule(
                    defaults.quantity.quantity_decimal_places, defaults.quantity.quantity_increment
                ).validate(entry.opening_quantity)
                if entry.manufactured_on and entry.manufactured_on > opening_date:
                    raise ValidationFailedError(
                        "Opening stock cannot precede manufacture",
                        fields={"manufactured_on": "Must be on or before the opening date"},
                    )
                if entry.expires_on and entry.expires_on < opening_date:
                    raise ValidationFailedError(
                        "Expired opening stock requires quarantine",
                        fields={"expires_on": "Must cover the opening date"},
                    )
            for key, mode in (
                ("purchase_price", config.pricing.purchase_reference_mode),
                ("mrp", config.pricing.mrp_mode),
            ):
                value = getattr(entry, key)
                if mode == "REQUIRED" and value is None:
                    raise ValidationFailedError(
                        "Enter the required batch price",
                        fields={key: "Required by Product Configuration"},
                    )
                if mode == "DISABLED" and value is not None:
                    raise ValidationFailedError(
                        "Batch price is disabled", fields={key: "Disabled by Product Configuration"}
                    )
            prices = await sale_amounts(access, config, today, entry)
            if entry.purchase_price is not None:
                if policy is None or policy.purchase_plan_id is None:
                    raise ConflictError("Complete the default purchase price book")
                plan = await access.reference(PricePlan, policy.purchase_plan_id)
                prices.append({"plan_id": plan.id, "amount": entry.purchase_price})
            for value in prices:
                value.update(
                    price_basis_quantity=Decimal("1"),
                    price_decimal_places=defaults.price.price_decimal_places,
                )
                plan = await access.reference(PricePlan, value["plan_id"])
                field = (
                    "purchase_price"
                    if plan.purpose == "PURCHASE"
                    else "sale_prices." + str(plan.price_level_id)
                    if entry.sale_prices
                    else "sale_price"
                )
                try:
                    RateGrid(
                        defaults.price.price_decimal_places, defaults.price.price_increment
                    ).entered(value["amount"])
                except (ValidationFailedError, MoneyError) as error:
                    raise ValidationFailedError(
                        "Batch price does not fit the configured price grid",
                        fields={
                            field: "Use a positive price on the configured price grid"
                        },
                    ) from error
                if (
                    entry.mrp is not None
                    and plan.purpose == "SALE"
                    and plan.tax_basis == "INCLUSIVE"
                    and value["amount"] > entry.mrp
                ):
                    raise ValidationFailedError(
                        "Selling price exceeds batch MRP",
                        fields={field: "Price including tax cannot exceed MRP"},
                    )
            if entry.mrp is not None:
                RateGrid(
                    defaults.price.price_decimal_places, defaults.price.price_increment
                ).entered(entry.mrp)
            result.append(
                {
                    "prices": [
                        InitialPrice.model_validate(value).model_dump(mode="json")
                        for value in prices
                    ]
                }
            )
        except PlatformError as error:
            error.extra["fields"] = {
                prefix + key: message
                for key, message in (error.extra.get("fields") or {"code": error.message}).items()
            }
            raise
        except MoneyError as error:
            raise ValidationFailedError(
                "Batch quantity does not fit the base unit",
                fields={prefix + "opening_quantity": "Use the base-unit precision and increment"},
            ) from error
    return result
