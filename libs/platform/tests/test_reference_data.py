"""The committed ISO datasets and the loader that validates them.

These are the highest-leverage tests in the reference layer. Every company, address
and invoice in the platform points at one of these rows by code, so a bad row is not
a display bug — a wrong `tax_jurisdiction_code` puts the wrong two digits in front of
a GSTIN, and a wrong `default_currency_code` pre-selects the wrong base currency on a
company that then cannot change it (invariant 16).

The datasets are generated, so these tests do not re-derive ISO. They assert the
things a regeneration could silently break: the shape matches the models, the
references close, nothing exceeds its column, and the curated Indian GST codes are
all still present.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from billing_platform.reference import (
    DATASETS,
    MODELS,
    ReferenceDataError,
    countries,
    currencies,
    load,
    load_all,
    primary_key_column,
    states,
)

#: A handful of rows checked by value rather than by shape. Chosen because each one
#: is load-bearing somewhere else in the platform: INR and its minor-unit names for
#: amount-in-words, JPY for the zero-decimal display path, KWD for three decimals,
#: and IN/GB for the jurisdiction profile.
_EXPECTED_CURRENCIES: dict[str, dict[str, Any]] = {
    "INR": {
        "numeric_code": "356",
        "minor_unit": 2,
        "major_unit_name": "Rupees",
        "minor_unit_name": "Paisa",
        "minor_unit_name_plural": "Paise",
    },
    "JPY": {"numeric_code": "392", "minor_unit": 0},
    "KWD": {"numeric_code": "414", "minor_unit": 3},
    "USD": {"numeric_code": "840", "minor_unit": 2},
}

_EXPECTED_COUNTRIES: dict[str, dict[str, Any]] = {
    "IN": {
        "iso3": "IND",
        "numeric_code": "356",
        "official_name": "Republic of India",
        "default_currency_code": "INR",
        "phone_prefix": "+91",
        "subdivision_label": "State",
    },
    "AE": {"default_currency_code": "AED", "phone_prefix": "+971", "subdivision_label": "Emirate"},
    "CA": {"default_currency_code": "CAD", "subdivision_label": "Province"},
}

#: The GST state codes that must survive any regeneration. Not the full 36 — that
#: list lives in the generator — but the ones a change would most likely disturb:
#: the two whose ISO spelling differs between editions (Telangana, Uttarakhand), the
#: newest subdivision (Ladakh), and the merged union territory.
_EXPECTED_GST: dict[str, str] = {
    "IN-MH": "27",
    "IN-KA": "29",
    "IN-TS": "36",
    "IN-UK": "05",
    "IN-LA": "38",
    "IN-DH": "26",
}


def test_every_dataset_loads() -> None:
    loaded = load_all()
    assert set(loaded) == set(DATASETS)
    assert all(rows for rows in loaded.values())


def test_datasets_are_in_foreign_key_order() -> None:
    """The seed applies them in this order, and `country` references `currency`."""
    assert DATASETS == ("currency", "country", "state")


@pytest.mark.parametrize("name", DATASETS)
def test_rows_match_the_model_columns_exactly(name: str) -> None:
    """A dataset key set that drifts from the model is what turns a regeneration
    into a ``TypeError`` partway through seeding a production database."""
    expected = {column.name for column in MODELS[name].__table__.columns}
    for row in load(name):
        assert set(row) == expected


@pytest.mark.parametrize("name", DATASETS)
def test_primary_keys_are_unique_and_non_empty(name: str) -> None:
    pk = primary_key_column(name)
    keys = [row[pk] for row in load(name)]
    assert all(keys)
    assert len(set(keys)) == len(keys)


@pytest.mark.parametrize("name", DATASETS)
def test_no_value_exceeds_its_column(name: str) -> None:
    """MariaDB truncates an over-long value on insert rather than raising, so a
    dataset one character too wide seeds silently wrong data. The generator refuses
    to write one; this holds the committed file to the same rule."""
    columns = MODELS[name].__table__.columns
    for row in load(name):
        for column_name, value in row.items():
            length = getattr(columns[column_name].type, "length", None)
            if length is None or value is None or isinstance(value, bool):
                continue
            assert len(str(value)) <= length, f"{name}.{column_name}={value!r}"


@pytest.mark.parametrize("name", DATASETS)
def test_no_column_declared_not_null_is_missing_a_value(name: str) -> None:
    columns = MODELS[name].__table__.columns
    for row in load(name):
        for column_name, value in row.items():
            if not columns[column_name].nullable:
                assert value is not None, f"{name}.{column_name} is NOT NULL but the row omits it"


def test_every_country_currency_exists() -> None:
    """Checked in Python as well as by the foreign key: the seed inserts `currency`
    first, and a dangling reference should fail before the first write rather than
    partway through the second table."""
    known = {row["code"] for row in currencies()}
    assert {row["default_currency_code"] for row in countries()} <= known


def test_every_state_country_exists() -> None:
    known = {row["code"] for row in countries()}
    assert {row["country_code"] for row in states()} <= known


@pytest.mark.parametrize(("code", "expected"), sorted(_EXPECTED_CURRENCIES.items()))
def test_known_currency_values(code: str, expected: dict[str, Any]) -> None:
    row = next(r for r in currencies() if r["code"] == code)
    assert {key: row[key] for key in expected} == expected


@pytest.mark.parametrize(("code", "expected"), sorted(_EXPECTED_COUNTRIES.items()))
def test_known_country_values(code: str, expected: dict[str, Any]) -> None:
    row = next(r for r in countries() if r["code"] == code)
    assert {key: row[key] for key in expected} == expected


@pytest.mark.parametrize(("code", "expected"), sorted(_EXPECTED_GST.items()))
def test_gst_state_codes_survive_regeneration(code: str, expected: str) -> None:
    """A dropped or renumbered GST code puts the wrong two digits in front of every
    GSTIN issued in that state, and nothing downstream would notice."""
    row = next(r for r in states() if r["code"] == code)
    assert row["tax_jurisdiction_code"] == expected


def test_every_indian_state_has_a_gst_code() -> None:
    """India is the launch jurisdiction: a subdivision with no GST code cannot be a
    place of supply, so a new ISO subdivision must fail here rather than at the
    first invoice."""
    missing = sorted(
        row["code"]
        for row in states()
        if row["country_code"] == "IN" and not row["tax_jurisdiction_code"]
    )
    assert missing == [], f"Indian subdivisions with no GST state code: {missing}"


def test_minor_units_are_within_the_stored_scale() -> None:
    """Display precision may never exceed the fixed storage scale of four decimals
    (``docs/identity-schema.md`` §0.4), or an amount would render digits the column
    cannot hold."""
    assert all(0 <= row["minor_unit"] <= 4 for row in currencies())


def test_no_currency_is_a_non_currency_iso_code() -> None:
    """ISO 4217 also assigns codes to precious metals, IMF drawing rights, bond
    market units, and "no currency involved". They are not selectable base
    currencies, so the generator drops them; `XOF` and `XCD` are real and stay."""
    codes = {row["code"] for row in currencies()}
    assert not codes & {"XXX", "XTS", "XAU", "XAG", "XPT", "XPD", "XDR", "XBA", "XSU"}
    assert {"XOF", "XAF", "XCD", "XPF"} <= codes


def test_currency_symbols_are_present() -> None:
    """The symbol is NOT NULL; a currency with no CLDR symbol falls back to its code
    rather than to an empty string, which would print an amount with no unit."""
    for row in currencies():
        assert row["symbol"].strip()


def test_reference_codes_are_upper_case() -> None:
    """Codes are matched by equality across services and never normalized at the
    boundary, so a lower-case one would silently fail every join."""
    assert all(row["code"].isupper() for row in currencies())
    assert all(row["code"].isupper() for row in countries())
    assert all(row["code"].isupper() for row in states())


def test_all_seeded_rows_start_active() -> None:
    """Deactivation is the seed's job when ISO withdraws a code, never a state the
    committed dataset ships in."""
    for name in DATASETS:
        assert all(row["is_active"] is True for row in load(name))


def test_load_rejects_an_unknown_dataset() -> None:
    with pytest.raises(ReferenceDataError, match="unknown reference dataset"):
        load("not_a_registered_dataset")


def test_load_returns_copies_the_caller_may_mutate() -> None:
    """The cache holds the parsed file; handing out the cached dicts would let one
    caller's edit leak into every later one."""
    first = load("currency")
    first[0]["name"] = "mutated"
    assert load("currency")[0]["name"] != "mutated"


def test_the_committed_files_are_sorted_by_primary_key() -> None:
    """Generated output is committed, so it must diff cleanly: an unsorted file
    turns a one-row ISO change into a whole-file diff no one reads."""
    for name in DATASETS:
        pk = primary_key_column(name)
        keys = [row[pk] for row in load(name)]
        assert keys == sorted(keys), f"{name}.json is not sorted by {pk}"


def test_the_committed_files_are_valid_utf8_json_with_a_trailing_newline() -> None:
    from importlib import resources

    for name in DATASETS:
        text = (
            resources.files("billing_platform.reference")
            .joinpath("data", f"{name}.json")
            .read_text(encoding="utf-8")
        )
        assert text.endswith("\n")
        assert isinstance(json.loads(text), list)
