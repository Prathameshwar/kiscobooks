"""Validate native ISO values against the platform's versioned local catalogue."""

from functools import cache

from billing_platform import reference
from billing_platform.errors import ValidationFailedError


@cache
def codes(dataset: str) -> frozenset[str]:
    return frozenset(row["code"] for row in reference.load(dataset) if row.get("is_active", True))


@cache
def tax_jurisdictions() -> dict[str, str]:
    return {
        row["code"]: row["tax_jurisdiction_code"]
        for row in reference.load("state")
        if row.get("is_active", True) and row.get("tax_jurisdiction_code")
    }


def validate_reference(
    country: str | None, state: str | None, currencies: list[str | None]
) -> None:
    if country is not None and country not in codes("country"):
        raise ValidationFailedError("unknown or inactive country")
    if state is not None and (
        state not in codes("state") or not country or not state.startswith(country + "-")
    ):
        raise ValidationFailedError("state does not belong to the selected country")
    if any(currency is not None and currency not in codes("currency") for currency in currencies):
        raise ValidationFailedError("unknown or inactive currency")
