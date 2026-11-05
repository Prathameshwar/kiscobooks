"""``domain/company_defaults`` — no database, no app (CLAUDE.md §7).

The cross-layer assertion lives here rather than in the domain module: ``domain/`` may not
import the ORM (CLAUDE.md §4), so "every suggested value is one the company model accepts"
can only be checked from a layer that is allowed to see both.
"""

from __future__ import annotations

from dataclasses import MISSING, fields

from identity.domain.company_defaults import (
    NEUTRAL_DEFAULTS,
    CompanySetupDefaults,
    setup_defaults,
)
from identity.models.company import (
    CURRENCY_SYMBOL_POSITIONS,
    DIGIT_GROUPINGS,
    NEGATIVE_FORMATS,
    ROUNDING_MODES,
    TAX_TREATMENTS,
)

ALLOWED = {
    "digit_grouping": DIGIT_GROUPINGS,
    "negative_format": NEGATIVE_FORMATS,
    "currency_symbol_position": CURRENCY_SYMBOL_POSITIONS,
    "rounding_mode": ROUNDING_MODES,
    "tax_treatment_default": TAX_TREATMENTS,
}
#: Every jurisdiction with a table of its own, plus the fallback path.
COUNTRIES = ["IN", "GB", "ZZ", ""]


def test_every_suggested_enum_value_is_one_the_company_model_accepts() -> None:
    """A suggestion the create endpoint would reject is worse than no suggestion."""
    for country in COUNTRIES:
        defaults = setup_defaults(country)
        for name, allowed in ALLOWED.items():
            assert getattr(defaults, name) in allowed, f"{country}.{name}"


def test_suggested_anchors_and_precisions_are_in_range() -> None:
    for country in COUNTRIES:
        defaults = setup_defaults(country)
        assert 1 <= defaults.fiscal_year_start_month <= 12
        # Never above 28: an anchor day a short month cannot hold would be clamped by
        # Accounting, so suggesting one would preview a span the server will not produce.
        assert 1 <= defaults.fiscal_year_start_day <= 28
        assert 0 <= defaults.amount_precision <= 4
        assert 0 <= defaults.quantity_precision <= 4
        assert defaults.default_payment_terms_days >= 0


def test_known_jurisdictions_keep_their_own_conventions() -> None:
    india = setup_defaults("IN")
    assert (india.fiscal_year_start_month, india.fiscal_year_start_day) == (4, 1)
    assert (india.timezone, india.digit_grouping) == ("Asia/Kolkata", "indian")
    # GST shows tax separately on the document; UK retail prices are VAT-inclusive.
    assert india.tax_treatment_default == "exclusive"
    britain = setup_defaults("GB")
    assert (britain.fiscal_year_start_month, britain.fiscal_year_start_day) == (4, 6)
    assert (britain.tax_treatment_default, britain.digit_grouping) == ("inclusive", "western")


def test_an_unprofiled_country_gets_the_neutral_set_rather_than_an_error() -> None:
    """A country with no jurisdiction profile is still a country to trade in."""
    assert setup_defaults("ZZ") == NEUTRAL_DEFAULTS
    assert setup_defaults("") == NEUTRAL_DEFAULTS
    assert NEUTRAL_DEFAULTS.timezone == "UTC"
    assert NEUTRAL_DEFAULTS.fiscal_year_start_month == 1


def test_defaults_are_immutable_and_fully_stated() -> None:
    """Frozen, so one caller cannot edit the table every other caller reads."""
    try:
        NEUTRAL_DEFAULTS.timezone = "Asia/Kolkata"  # type: ignore[misc]  # proving it is frozen
    except AttributeError:
        pass
    else:  # pragma: no cover - only runs if the dataclass stops being frozen
        raise AssertionError("company setup defaults must be immutable")
    # No field may carry a dataclass-level default: a jurisdiction that silently
    # inherited "whatever the class says" is how a form suggests UTC in Mumbai.
    assert all(
        field.default is MISSING and field.default_factory is MISSING
        for field in fields(CompanySetupDefaults)
    )
