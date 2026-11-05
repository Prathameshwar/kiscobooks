"""Closed controls over existing price dimensions and methods."""

from billing_platform.errors import ConflictError

PRICING_DIMENSIONS = {
    "multiple_price_levels_mode": "Multiple selling-price levels",
    "unit_prices_mode": "Separate unit/pack prices",
    "quantity_tiers_mode": "Quantity-slab prices",
    "channel_prices_mode": "Sales-channel prices",
    "additional_currencies_mode": "Additional pricing currencies",
    "formula_prices_mode": "Formula prices",
}


def require_dimension(mode: str, field: str) -> None:
    if mode != "ENABLED":
        raise ConflictError(f"{PRICING_DIMENSIONS[field]} are disabled by Product Configuration")
