"""Read-only company setup choices, sourced from installation seeds and profiles."""

from __future__ import annotations

from pydantic import Field

from identity.schemas.base import StrictModel


class CountrySetupDefaults(StrictModel):
    """A starting point for a new company in this country, never a decision.

    ``POST /v1/companies`` still requires every one of these explicitly. Served here so
    that a setup form does not carry its own table of jurisdiction conventions
    (``identity.domain.company_defaults``).
    """

    fiscal_year_start_month: int
    fiscal_year_start_day: int
    timezone: str
    locale: str
    date_format: str
    datetime_format: str
    digit_grouping: str
    decimal_separator: str
    thousands_separator: str
    negative_format: str
    currency_symbol_position: str
    amount_precision: int
    quantity_precision: int
    rounding_mode: str
    tax_treatment_default: str
    default_payment_terms_days: int


class TaxRegimeChoice(StrictModel):
    value: str
    label: str


class TaxRegistrationChoice(StrictModel):
    tax_system: str
    number_label: str
    jurisdiction_scope: str
    regimes: list[TaxRegimeChoice]


class CountryChoice(StrictModel):
    code: str
    name: str
    default_currency_code: str
    subdivision_label: str
    jurisdiction_supported: bool
    tax_systems: list[str]
    tax_registration_options: list[TaxRegistrationChoice] = Field(default_factory=list)
    #: Capability keys a setup form offers **already selected** for this
    #: jurisdiction (docs/company-features.md §3). A suggestion from the
    #: jurisdiction profile, not a decision: nothing is enabled until the caller
    #: asks for it, and an unsupported jurisdiction suggests nothing.
    default_features: list[str]
    setup_defaults: CountrySetupDefaults


class StateChoice(StrictModel):
    code: str
    country_code: str
    name: str


class CurrencyChoice(StrictModel):
    code: str
    name: str
    symbol: str
    minor_unit: int


class LicenceTypeChoice(StrictModel):
    kind: str
    label: str
    valid_to_required: bool
    prints_on_invoice: bool


class TimezoneChoice(StrictModel):
    """Installation-maintained IANA identifiers; offsets depend on the instant."""

    code: str
    name: str
    is_active: bool
