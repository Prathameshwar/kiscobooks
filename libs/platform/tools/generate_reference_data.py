"""Regenerate the static ISO reference datasets.

Run by hand when the ISO lists change — roughly yearly — never at runtime and never
in CI:

    python -m uv run --group reference python tools/generate_reference_data.py

**Why a generator and committed JSON rather than a runtime dependency.**
`docs/tech-stack.md` § *Reference tables* makes `libs/platform` the source of truth
for tier-1 data, materialized into each service database by a seed. Three things
follow from that:

* The data must be *versioned in the repo*, so a seed is reproducible and a change
  to a country name is a reviewable diff rather than a silent consequence of a
  dependency bump.
* It must not be a runtime dependency of seven services (CLAUDE.md §5.15).
* It must not be hand-transcribed. 249 countries, ~5000 subdivisions and ~180
  currencies typed by hand would contain errors, in tables that other tables carry
  foreign keys to.

So the authoritative databases are read at generation time only:

* `pycountry` — ISO 3166-1, ISO 3166-2 and ISO 4217, vendored from Debian's
  `iso-codes`.
* `babel` — CLDR, for currency symbols, minor units and territory currencies.
* `phonenumbers` — libphonenumber, for dial codes.

All three are in the `reference` dependency group and are not installed in
production.

Anything the databases cannot supply is **derived by a documented rule or curated
explicitly below** — never guessed. A country missing data for a NOT NULL column is
excluded from the dataset and reported, because a wrong dial code in a reference
table is worse than an absent country.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import phonenumbers
import pycountry
from babel import Locale
from babel.core import get_global
from babel.numbers import get_currency_name, get_currency_symbol

_DATA_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "billing_platform" / "reference" / "data"
)

#: Minor-unit names are not in CLDR in any systematic form, and the column is
#: nullable for that reason. Curated only where amount-in-words actually needs it.
_MINOR_UNIT_NAMES: dict[str, tuple[str, str]] = {
    "AED": ("Fils", "Fils"),
    "AUD": ("Cent", "Cents"),
    "BHD": ("Fils", "Fils"),
    "CAD": ("Cent", "Cents"),
    "CHF": ("Rappen", "Rappen"),
    "EUR": ("Cent", "Cents"),
    "GBP": ("Penny", "Pence"),
    "INR": ("Paisa", "Paise"),
    "KWD": ("Fils", "Fils"),
    "LKR": ("Cent", "Cents"),
    "MYR": ("Sen", "Sen"),
    "NPR": ("Paisa", "Paise"),
    "OMR": ("Baisa", "Baisa"),
    "PKR": ("Paisa", "Paise"),
    "QAR": ("Dirham", "Dirhams"),
    "SAR": ("Halala", "Halalas"),
    "SGD": ("Cent", "Cents"),
    "USD": ("Cent", "Cents"),
    "ZAR": ("Cent", "Cents"),
}

#: GST state codes, the first two digits of every GSTIN issued in that state.
#: Statutory, stable, and not in any ISO database, so curated. Keyed by ISO 3166-2
#: code and validated against `pycountry` below: a code that no longer exists is a
#: hard failure, not a silently dropped row. That check has already earned its
#: keep — the bundled `iso-codes` edition spells three of these IN-CG, IN-TS and
#: IN-UK where other ISO editions use IN-CT, IN-TG and IN-UT.
_GST_STATE_CODES: dict[str, str] = {
    "IN-JK": "01",
    "IN-HP": "02",
    "IN-PB": "03",
    "IN-CH": "04",
    "IN-UK": "05",
    "IN-HR": "06",
    "IN-DL": "07",
    "IN-RJ": "08",
    "IN-UP": "09",
    "IN-BR": "10",
    "IN-SK": "11",
    "IN-AR": "12",
    "IN-NL": "13",
    "IN-MN": "14",
    "IN-MZ": "15",
    "IN-TR": "16",
    "IN-ML": "17",
    "IN-AS": "18",
    "IN-WB": "19",
    "IN-JH": "20",
    "IN-OD": "21",
    "IN-CG": "22",
    "IN-MP": "23",
    "IN-GJ": "24",
    "IN-DH": "26",
    "IN-MH": "27",
    "IN-KA": "29",
    "IN-GA": "30",
    "IN-LD": "31",
    "IN-KL": "32",
    "IN-TN": "33",
    "IN-PY": "34",
    "IN-AN": "35",
    "IN-TS": "36",
    "IN-AP": "37",
    "IN-LA": "38",
}

#: ISO 3166-2 uses sentence case for subdivision types ("union territory"); the
#: column is a UI label, so it is title-cased. Ordering matters where a country has
#: several types: the *modal* type wins, which gives "State" for IN, "Province" for
#: CA, "Emirate" for AE.
_FALLBACK_SUBDIVISION_LABEL = "Region"


def _log(message: str) -> None:
    print(message, file=sys.stderr)  # noqa: T201  a generator's only output channel


def _currency_minor_units() -> dict[str, int]:
    fractions: dict[str, Any] = dict(get_global("currency_fractions") or {})
    default_digits = int(fractions.get("DEFAULT", (2,))[0])
    return {code: int(value[0]) for code, value in fractions.items() if code != "DEFAULT"} | {
        "__default__": default_digits
    }


def _major_unit_name(code: str) -> str:
    """ "Indian rupees" -> "Rupees"; "euros" -> "Euros".

    The plural CLDR name minus its territorial qualifier. It is a display string for
    amount-in-words, not an identifier, so a wrong-looking one is a cosmetic fix
    rather than a data-integrity problem.
    """
    plural = get_currency_name(code, count=2, locale="en")
    if plural == code:
        return code
    return plural.split()[-1].capitalize()


def _legal_tender_codes() -> set[str]:
    """Every currency CLDR records as legal tender in some territory, ever.

    Used to drop the ISO 4217 ``X`` codes that are not currencies — ``XXX`` (no
    currency), ``XTS`` (testing), ``XAU``/``XAG``/``XPD``/``XPT`` (metals),
    ``XDR`` (IMF special drawing rights), ``XBA`` to ``XBD`` (bond market units).
    They are valid ISO codes and would otherwise appear in the currency dropdown,
    where "the code assigned for transactions where no currency is involved" is a
    selectable base currency for a company. Derived rather than curated: the real
    ``X`` currencies — ``XOF``, ``XAF``, ``XCD``, ``XPF`` — are legal tender and
    survive the same rule.
    """
    territory_currencies: dict[str, Any] = dict(get_global("territory_currencies") or {})
    return {
        str(code)
        for entries in territory_currencies.values()
        for code, _start, _end, is_tender in entries
        if is_tender
    }


def build_currencies() -> list[dict[str, Any]]:
    minor_units = _currency_minor_units()
    default_minor = minor_units["__default__"]
    legal_tender = _legal_tender_codes()
    rows: list[dict[str, Any]] = []

    for currency in sorted(pycountry.currencies, key=lambda c: c.alpha_3):
        code = currency.alpha_3
        numeric = getattr(currency, "numeric", None)
        if numeric is None:
            _log(f"currency {code}: no ISO numeric code, excluded")
            continue
        if code.startswith("X") and code not in legal_tender:
            _log(f"currency {code}: not legal tender in any territory, excluded")
            continue
        minor_name = _MINOR_UNIT_NAMES.get(code)
        rows.append(
            {
                "code": code,
                "numeric_code": str(numeric).zfill(3),
                "name": currency.name,
                "symbol": get_currency_symbol(code, locale="en"),
                "minor_unit": minor_units.get(code, default_minor),
                "major_unit_name": _major_unit_name(code),
                "minor_unit_name": minor_name[0] if minor_name else None,
                "minor_unit_name_plural": minor_name[1] if minor_name else None,
                "is_active": True,
            }
        )
    return rows


def _current_currency(alpha_2: str) -> str | None:
    """The territory's current legal tender, per CLDR.

    Entries are ``(code, start, end, is_tender)``. A territory can have several with
    no end date — Zimbabwe lists both USD and ZWG — so the most recently *introduced*
    one wins rather than the first in the list, which would pick USD there.
    """
    territory_currencies: dict[str, Any] = dict(get_global("territory_currencies") or {})
    current = [
        (start or (0, 1, 1), str(code))
        for code, start, end, is_tender in territory_currencies.get(alpha_2, [])
        if end is None and is_tender
    ]
    if not current:
        return None
    return max(current)[1]


def _subdivision_label(alpha_2: str) -> str:
    # `type: ignore` because pycountry ships no stubs and its lookup helpers are
    # untyped; the shape is checked by the reference tests instead.
    found = pycountry.subdivisions.get(country_code=alpha_2)  # type: ignore[no-untyped-call]
    subdivisions = found or []
    counts: dict[str, int] = {}
    for subdivision in subdivisions:
        counts[subdivision.type] = counts.get(subdivision.type, 0) + 1
    if not counts:
        return _FALLBACK_SUBDIVISION_LABEL
    modal = max(counts.items(), key=lambda item: (item[1], item[0]))[0]
    return modal[:1].upper() + modal[1:]


def build_countries(currency_codes: set[str]) -> tuple[list[dict[str, Any]], set[str]]:
    """Returns the rows, plus the alpha-2 codes that were excluded."""
    rows: list[dict[str, Any]] = []
    excluded: set[str] = set()

    for country in sorted(pycountry.countries, key=lambda c: c.alpha_2):
        alpha_2 = country.alpha_2

        currency_code = _current_currency(alpha_2)
        if currency_code is None or currency_code not in currency_codes:
            _log(f"country {alpha_2}: no current ISO currency, excluded")
            excluded.add(alpha_2)
            continue

        dial_code = phonenumbers.country_code_for_region(alpha_2)
        if not dial_code:
            # Uninhabited or dependent territories with no dial code. `phone_prefix`
            # is NOT NULL, and an empty string would be a lie, so the row is left
            # out: a company cannot be registered there.
            _log(f"country {alpha_2}: no dial code, excluded")
            excluded.add(alpha_2)
            continue

        rows.append(
            {
                "code": alpha_2,
                "iso3": country.alpha_3,
                "numeric_code": str(country.numeric).zfill(3),
                "name": getattr(country, "common_name", None) or country.name,
                "official_name": getattr(country, "official_name", None) or country.name,
                "default_currency_code": currency_code,
                "phone_prefix": f"+{dial_code}",
                "subdivision_label": _subdivision_label(alpha_2),
                "is_active": True,
            }
        )
    return rows, excluded


def build_states(excluded_countries: set[str]) -> list[dict[str, Any]]:
    unknown = sorted(
        code
        for code in _GST_STATE_CODES
        # See `_subdivision_label`: pycountry is unstubbed.
        if pycountry.subdivisions.get(code=code) is None  # type: ignore[no-untyped-call]
    )
    if unknown:
        raise SystemExit(
            f"curated GST codes reference ISO 3166-2 codes that no longer exist: {unknown}. "
            "Reconcile the map before regenerating; a dropped row would silently break "
            "GSTIN validation."
        )

    rows: list[dict[str, Any]] = []
    for subdivision in sorted(pycountry.subdivisions, key=lambda s: s.code):
        if subdivision.country_code in excluded_countries:
            continue
        if len(subdivision.code) > 6:
            # `state.code` is VARCHAR(6). A handful of ISO 3166-2 codes are longer;
            # widening the PK is a schema change, so they are reported, not truncated.
            _log(f"subdivision {subdivision.code}: longer than 6 characters, excluded")
            continue
        rows.append(
            {
                "code": subdivision.code,
                "country_code": subdivision.country_code,
                "name": subdivision.name,
                "subdivision_type": subdivision.type,
                "tax_jurisdiction_code": _GST_STATE_CODES.get(subdivision.code),
                "is_active": True,
            }
        )
    return rows


#: The ``VARCHAR``/``CHAR`` width of every text column, from
#: ``docs/identity-schema.md`` §1.1 to §1.3. Checked here because MariaDB in its
#: default mode *truncates* an over-long value on insert rather than raising, so a
#: name one character too long would seed silently wrong. This check is what found
#: "Metropolitan collectivity with special status" at 45 characters against a
#: `VARCHAR(40)` `subdivision_type`.
_COLUMN_WIDTHS: dict[str, dict[str, int]] = {
    "currency": {
        "code": 3,
        "numeric_code": 3,
        "name": 100,
        "symbol": 8,
        "major_unit_name": 40,
        "minor_unit_name": 40,
        "minor_unit_name_plural": 40,
    },
    "country": {
        "code": 2,
        "iso3": 3,
        "numeric_code": 3,
        "name": 100,
        "official_name": 200,
        "default_currency_code": 3,
        "phone_prefix": 8,
        "subdivision_label": 60,
    },
    "state": {
        "code": 6,
        "country_code": 2,
        "name": 100,
        "subdivision_type": 60,
        "tax_jurisdiction_code": 8,
    },
}


def _check_widths(name: str, rows: list[dict[str, Any]]) -> None:
    widths = _COLUMN_WIDTHS[name]
    for row in rows:
        for column, width in widths.items():
            value = row[column]
            if value is not None and len(str(value)) > width:
                raise SystemExit(
                    f"{name}.{column} is VARCHAR({width}) but row {row['code']!r} needs "
                    f"{len(str(value))}: {value!r}. Widen the column in the schema doc, the "
                    "model and a migration — never truncate reference data."
                )


def _write(name: str, rows: list[dict[str, Any]]) -> None:
    _check_widths(name, rows)
    path = _DATA_DIR / f"{name}.json"
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    _log(f"wrote {len(rows):5d} rows to {path.name}")


def main() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Asserted so a Babel or pycountry upgrade that changes locale handling fails
    # here rather than producing subtly different display strings.
    assert Locale.parse("en").language == "en"

    currencies = build_currencies()
    countries, excluded = build_countries({row["code"] for row in currencies})
    states = build_states(excluded)

    _write("currency", currencies)
    _write("country", countries)
    _write("state", states)
    _log(f"excluded {len(excluded)} countries; see the messages above for each reason")


if __name__ == "__main__":
    main()
