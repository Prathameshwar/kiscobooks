"""What a jurisdiction usually implies for a new company — **suggestions, never decisions**.

``POST /v1/companies`` guesses nothing (docs/company-setup.md): country, currency, tax
system, the financial-year anchor and the display conventions are all explicit on the
request. What a setup form needs is somewhere to *start*, so that an operator confirms
fifteen fields instead of typing them, and that starting point has to come from the
company's jurisdiction rather than from the browser's locale — an Indian company opened
from a laptop in Berlin still prints ``12,34,567.89`` and ``dd-MM-yyyy`` (CLAUDE.md §4:
display config comes from config, never from client locale defaults).

These were a table inside the console wizard during the UI phase, which made them a
client's private copy of facts about a jurisdiction. They are served on
``GET /v1/reference/countries`` now, so every client — web, mobile, and the next one —
suggests the same thing.

They are deliberately **not** on ``billing_platform.jurisdiction``. That profile carries
what other services replicate: which statutory identifiers exist, what they look like,
the cash ceiling. A fiscal anchor and a date format are read by exactly one service, at
one moment, to pre-fill one form; replicating them into ``vouchers`` and ``reports``
would imply they govern something there, and nothing reads a suggestion after creation.

No framework and no ORM (CLAUDE.md §4). The enum-valued fields are plain strings here;
``tests/test_company_defaults_domain.py`` asserts every one of them is in the set the
company model accepts, which is the check that cannot live in this layer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final


@dataclass(frozen=True, slots=True)
class CompanySetupDefaults:
    """One jurisdiction's starting point for the fields a new company must state."""

    #: The financial year's anchor. ``fiscal_year_start_day`` is clamped to the month's
    #: length by Accounting when it generates the periods, never here.
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
    #: Display and rounding scale only. Storage is ``DECIMAL(19,4)`` everywhere
    #: regardless of what a company shows (CLAUDE.md §4).
    amount_precision: int
    quantity_precision: int
    rounding_mode: str
    tax_treatment_default: str
    default_payment_terms_days: int


#: The fallback for a country with no profile of its own: ISO-ish, western grouping, tax
#: shown separately. An operator is expected to review every line of it.
NEUTRAL_DEFAULTS: Final[CompanySetupDefaults] = CompanySetupDefaults(
    fiscal_year_start_month=1,
    fiscal_year_start_day=1,
    timezone="UTC",
    locale="en",
    date_format="dd MMM yyyy",
    datetime_format="dd MMM yyyy HH:mm",
    digit_grouping="western",
    decimal_separator=".",
    thousands_separator=",",
    negative_format="minus",
    currency_symbol_position="prefix",
    amount_precision=2,
    quantity_precision=3,
    rounding_mode="half_up",
    tax_treatment_default="exclusive",
    default_payment_terms_days=30,
)

_BY_COUNTRY: Final[dict[str, CompanySetupDefaults]] = {
    # April-March, Indian digit grouping, and the GST convention of showing tax
    # separately on the document.
    "IN": replace(
        NEUTRAL_DEFAULTS,
        fiscal_year_start_month=4,
        fiscal_year_start_day=1,
        timezone="Asia/Kolkata",
        date_format="dd-MM-yyyy",
        datetime_format="dd-MM-yyyy HH:mm",
        digit_grouping="indian",
    ),
    # April-March too, but from the 6th, with western grouping and VAT-inclusive
    # retail pricing.
    "GB": replace(
        NEUTRAL_DEFAULTS,
        fiscal_year_start_month=4,
        fiscal_year_start_day=6,
        timezone="Europe/London",
        date_format="dd/MM/yyyy",
        datetime_format="dd/MM/yyyy HH:mm",
        tax_treatment_default="inclusive",
    ),
}


def setup_defaults(country_code: str) -> CompanySetupDefaults:
    """This country's starting point, or the neutral one.

    Never raises on an unknown country: a country with no jurisdiction profile is still
    a country a company may be created in, and refusing to suggest anything would be
    read as "this country is not supported".
    """
    return _BY_COUNTRY.get(country_code, NEUTRAL_DEFAULTS)
