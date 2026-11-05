"""Enforce existing pricing capabilities against the effective product configuration."""

import uuid

from catalog.domain.pricing_dimensions import require_dimension
from catalog.models.pricing import PricePlan
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.tasks.configuration_access import ConfigurationAccess


async def validate_dimensions(
    access: ConfigurationAccess,
    config: EffectiveConfiguration,
    *,
    base_unit_id: uuid.UUID,
    unit_id: uuid.UUID,
    currency: str,
    channel_code: str | None = None,
    price_method: str = "FIXED",
    price_level_ordinal: int = 1,
) -> None:
    context = await access.context(PricePlan)
    used = {
        "multiple_price_levels_mode": price_level_ordinal != 1,
        "unit_prices_mode": unit_id != base_unit_id,
        "quantity_tiers_mode": price_method == "TIERS",
        "channel_prices_mode": channel_code is not None,
        "additional_currencies_mode": currency != context.company.base_currency,
        "formula_prices_mode": price_method == "FORMULA",
    }
    for field, enabled in used.items():
        if enabled:
            require_dimension(getattr(config.pricing, field), field)
