"""Resolve Simple selling amounts to existing, protected company price books."""

import datetime as dt
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select

from catalog.models.pricing import CompanyPricingPolicy, PriceLevel, PricePlan
from catalog.models.products import Item
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.schemas.simple_product_creation import (
    SimpleBatchInput,
    SimpleCreationInput,
    SimpleSalePriceOption,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import effective, protected


async def multiple_enabled(access: ConfigurationAccess, config: EffectiveConfiguration) -> bool:
    if config.pricing.multiple_price_levels_mode == "DISABLED":
        return False
    context = await access.context(Item)
    return "multi_price_levels" in context.features


async def sale_choices(
    access: ConfigurationAccess, config: EffectiveConfiguration, today: dt.date
) -> list[SimpleSalePriceOption]:
    if config.pricing.sale_price_mode == "DISABLED" or not await multiple_enabled(access, config):
        return []
    policy = await effective(access, CompanyPricingPolicy, today)
    if policy is None:
        raise ConflictError("Complete company pricing defaults before entering selling prices")
    await protected(access, PriceLevel)
    await protected(access, PricePlan)
    levels = list(
        await access.db.scalars(
            select(PriceLevel)
            .where(PriceLevel.company_id == access.company, PriceLevel.is_active.is_(True))
            .order_by(PriceLevel.ordinal)
            .limit(65)
        )
    )
    if len(levels) > 64:
        raise ConflictError("Selling-price levels exceed the supported limit")
    required = config.pricing.sale_price_mode == "REQUIRED"
    count = config.pricing.sale_level_count or 1
    if required and not set(range(1, count + 1)) <= {level.ordinal for level in levels}:
        raise ConflictError("Set up the required active selling-price levels in company pricing")
    if policy.default_level_id not in {level.id for level in levels}:
        raise ConflictError("Choose an active default selling-price level in company pricing")
    context = await access.context(PricePlan)
    plans = list(
        await access.db.scalars(
            select(PricePlan)
            .where(
                PricePlan.company_id == access.company,
                PricePlan.purpose == "SALE",
                PricePlan.currency == context.company.base_currency,
                PricePlan.price_level_id.in_([level.id for level in levels]),
            )
            .limit(65)
        )
    )
    by_level = {plan.price_level_id: plan for plan in plans}
    choices = []
    for level in levels:
        await access.require(level)
        needed = required and (level.ordinal <= count or level.id == policy.default_level_id)
        plan = by_level.get(level.id)
        if plan is None:
            if needed or level.id == policy.default_level_id:
                raise ConflictError(
                    "Set up a company-currency selling price book for " + level.name
                )
            continue
        await access.require(plan)
        choices.append(
            SimpleSalePriceOption.model_validate(
                {
                    "price_level_id": level.id,
                    "plan_id": plan.id,
                    "code": level.code,
                    "name": level.name,
                    "ordinal": level.ordinal,
                    "tax_basis": plan.tax_basis,
                    "required": needed,
                    "is_default": level.id == policy.default_level_id,
                }
            )
        )
    return choices


async def sale_amounts(
    access: ConfigurationAccess,
    config: EffectiveConfiguration,
    today: dt.date,
    body: SimpleCreationInput | SimpleBatchInput,
) -> list[dict[str, Any]]:
    mode = config.pricing.sale_price_mode
    if mode == "DISABLED":
        if body.sale_prices or body.sale_price is not None:
            raise ValidationFailedError(
                "Selling prices are disabled",
                fields={"sale_price": "Disabled by product configuration"},
            )
        return []
    if not body.sale_prices and body.sale_price is None and mode != "REQUIRED":
        return []
    if await multiple_enabled(access, config):
        choices = await sale_choices(access, config, today)
        selected = {price.price_level_id: price.amount for price in body.sale_prices}
        if body.sale_price is not None:
            selected[next(choice.price_level_id for choice in choices if choice.is_default)] = (
                body.sale_price
            )
        available = {choice.price_level_id for choice in choices}
        if selected.keys() - available:
            for identity in selected.keys() - available:
                # Keep the native foreign-company/read-deny boundary before choice validation.
                await access.reference(PriceLevel, identity)
            raise ValidationFailedError(
                "Choose an available selling-price level",
                fields={"sale_prices": "A selected selling-price level is unavailable"},
            )
        missing = {
            "sale_prices." + str(choice.price_level_id): "Required by product configuration"
            for choice in choices
            if choice.required and choice.price_level_id not in selected
        }
        if missing:
            raise ValidationFailedError("Enter the required selling prices", fields=missing)
        return [
            {"plan_id": choice.plan_id, "amount": selected[choice.price_level_id]}
            for choice in choices
            if choice.price_level_id in selected
        ]
    if body.sale_prices:
        raise ValidationFailedError(
            "Multiple selling-price levels are disabled",
            fields={
                "sale_prices": "Enable multiple selling-price levels and the company capability"
            },
        )
    if body.sale_price is None:
        raise ValidationFailedError(
            "Enter the required price", fields={"sale_price": "Required by product configuration"}
        )
    policy = await effective(access, CompanyPricingPolicy, today)
    if policy is None:
        raise ConflictError("Complete company pricing defaults")
    context = await access.context(PricePlan)
    plan = await access.db.scalar(
        select(PricePlan).where(
            PricePlan.company_id == access.company,
            PricePlan.currency == context.company.base_currency,
            PricePlan.price_level_id == policy.default_level_id,
            PricePlan.purpose == "SALE",
        )
    )
    if plan is None:
        raise ConflictError("The default selling price book is unavailable")
    await access.require(plan)
    return [{"plan_id": plan.id, "amount": body.sale_price}]
