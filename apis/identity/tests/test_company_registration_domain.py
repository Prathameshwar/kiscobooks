"""Writing a tax registration or a licence — the write path, with no database.

Resolution lives in ``billing_platform.statutory`` because ``billing`` needs it inside
the posting transaction and may not call ``identity`` to get it (CLAUDE.md invariant 7).
What is tested here is what a row must satisfy *before it exists*, which is
``identity``'s alone:

* what a registration *is* (``tax_system``, ``regime``, ``number``,
  ``jurisdiction_code``, ``valid_from``) is immutable after create, as a 422 rather
  than a 403 — no role can lift it, so it is not an authorization outcome;
* at most one ``is_primary`` per ``(tax_system, jurisdiction)`` on any date;
* the composition of every other check, in one call, so a route cannot skip one;
* **``existing`` is the company's other registrations**, since an amendment compared
  against itself always overlaps.
"""

from __future__ import annotations

import datetime as dt
import inspect

import pytest
from billing_platform.errors import ConflictError, ImmutableFieldError, ValidationFailedError
from billing_platform.statutory import Licence, TaxRegistration

from identity.domain import (
    REGISTRATION_IMMUTABLE_FIELDS,
    assert_licence_writable,
    assert_registration_coexists,
    assert_registration_writable,
    assert_single_primary,
    registration_changes,
    registration_class_of,
)

INDIAN_STATES = {"MH": "27", "KA": "29", "TN": "33", "DL": "07"}
APRIL = dt.date(2026, 4, 1)
SEPTEMBER_30 = dt.date(2026, 9, 30)
OCTOBER = dt.date(2026, 10, 1)


def registration(
    *,
    number: str = "27AAAPA1234A1ZT",
    tax_system: str = "gst_in",
    regime: str = "regular",
    jurisdiction_code: str = "MH",
    valid_from: dt.date = APRIL,
    valid_to: dt.date | None = None,
    is_primary: bool = False,
) -> TaxRegistration:
    return TaxRegistration(
        tax_system=tax_system,
        regime=regime,
        number=number,
        jurisdiction_code=jurisdiction_code,
        valid_from=valid_from,
        valid_to=valid_to,
        is_primary=is_primary,
    )


def _gstin(first14: str) -> str:
    """Append a mod-36 check character, computed independently of the platform."""
    total = 0
    for index, char in enumerate(first14):
        quotient, remainder = divmod(int(char, 36) * (2 if index % 2 else 1), 36)
        total += quotient + remainder
    return first14 + "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[(36 - total % 36) % 36]


def test_the_fixture_gstins_carry_valid_check_characters() -> None:
    for number in ("27AAAPA1234A1ZT", "27AAAPA1234A2ZS", "29AAAPA1234A1ZP"):
        assert _gstin(number[:14]) == number


def licence(
    *,
    kind: str = "drug_licence_20b",
    number: str = "MH-MUM-20B-4471",
    valid_from: dt.date = APRIL,
    valid_to: dt.date | None = dt.date(2031, 3, 31),
) -> Licence:
    return Licence(kind=kind, number=number, valid_from=valid_from, valid_to=valid_to)


# --- what a registration is, is immutable ----------------------------------------

CURRENT = {
    "tax_system": "gst_in",
    "regime": "composition",
    "number": "27AAAPA1234A1ZT",
    "jurisdiction_code": "MH",
    "valid_from": APRIL,
    "valid_to": None,
    "is_primary": True,
    "legal_name_on_registration": None,
}


def test_the_immutable_set_is_the_documented_one() -> None:
    assert (
        frozenset({"tax_system", "regime", "number", "jurisdiction_code", "valid_from"})
        == REGISTRATION_IMMUTABLE_FIELDS
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tax_system", "vat_gb"),
        ("regime", "regular"),
        ("number", "27AAAPA1234A2ZS"),
        ("jurisdiction_code", "KA"),
        ("valid_from", OCTOBER),
    ],
)
def test_changing_an_identity_field_in_place_is_refused(field: str, value: object) -> None:
    """Amending it would silently reinterpret every document already issued under the
    row: the framework or regime that computed a filed return, the GSTIN printed on it,
    or the state that made it intra- or inter-state."""
    with pytest.raises(ImmutableFieldError) as raised:
        registration_changes(CURRENT, {field: value})

    assert raised.value.extra["fields"] == {field: "immutable after create"}


def test_the_refusal_says_what_to_do_instead() -> None:
    """A regime change is close-and-reopen, which keeps old documents resolvable by
    ``posting_date``."""
    with pytest.raises(ImmutableFieldError) as raised:
        registration_changes(CURRENT, {"regime": "regular"})

    assert "add a new one" in str(raised.value)
    assert "valid_to" in str(raised.value)


def test_immutability_is_a_422_and_not_a_403() -> None:
    """No actor and no role can lift it, so it is not an authorization outcome — and a
    403 would send the caller looking for the permission that grants it, of which there
    is none."""
    with pytest.raises(ImmutableFieldError) as raised:
        registration_changes(CURRENT, {"tax_system": "none"})

    assert raised.value.status_code == 422
    assert raised.value.code == "immutable_field"


def test_every_changed_immutable_field_is_reported_together() -> None:
    with pytest.raises(ImmutableFieldError) as raised:
        registration_changes(CURRENT, {"regime": "regular", "valid_from": OCTOBER})

    assert set(raised.value.extra["fields"]) == {"regime", "valid_from"}


def test_echoing_unchanged_identity_fields_is_not_an_edit() -> None:
    """Judged on the diff, not on payload presence; the number compares normalized."""
    changes = registration_changes(
        CURRENT,
        {
            "regime": "composition",
            "number": "27aaapa1234a1zt",
            "jurisdiction_code": "MH",
            "valid_from": APRIL,
            "valid_to": SEPTEMBER_30,
        },
    )

    assert changes == {"valid_to": SEPTEMBER_30}


def test_the_amendable_fields_pass_and_only_real_changes_are_returned() -> None:
    changes = registration_changes(
        CURRENT,
        {
            "valid_to": SEPTEMBER_30,
            "is_primary": True,
            "legal_name_on_registration": "Alpha Traders",
        },
    )

    assert changes == {"valid_to": SEPTEMBER_30, "legal_name_on_registration": "Alpha Traders"}


# --- one primary per (tax_system, jurisdiction) on any date -----------------------


def test_two_primaries_in_one_state_at_once_are_refused() -> None:
    with pytest.raises(ConflictError) as raised:
        assert_single_primary(
            [
                registration(is_primary=True),
                registration(regime="tds_deductor", is_primary=True, valid_from=OCTOBER),
            ]
        )

    assert "primary" in str(raised.value)


def test_successive_primaries_are_allowed() -> None:
    assert_single_primary(
        [
            registration(is_primary=True, valid_to=SEPTEMBER_30),
            registration(is_primary=True, valid_from=OCTOBER),
        ]
    )


def test_primaries_in_different_states_or_systems_are_allowed() -> None:
    assert_single_primary(
        [
            registration(is_primary=True),
            registration(is_primary=True, jurisdiction_code="KA"),
            registration(is_primary=True, tax_system="vat_gb", jurisdiction_code="MH"),
        ]
    )


def test_a_non_primary_beside_a_primary_is_allowed() -> None:
    assert_single_primary([registration(is_primary=True), registration(regime="isd")])


def test_the_coexistence_check_includes_the_primary_rule() -> None:
    """The amendment path calls this alone, so it must carry the primary rule too."""
    with pytest.raises(ConflictError):
        assert_registration_coexists(
            incoming=registration(regime="tds_deductor", is_primary=True),
            existing=(registration(is_primary=True),),
        )


def test_the_coexistence_check_rejects_a_backwards_window() -> None:
    with pytest.raises(ValidationFailedError):
        assert_registration_coexists(
            incoming=registration(valid_from=OCTOBER, valid_to=APRIL), existing=()
        )


# --- the composed write check --------------------------------------------------


def test_a_valid_first_registration_passes_and_returns_its_stored_number() -> None:
    """The return value exists so the caller stores the string that was validated rather
    than the one that was typed."""
    stored = assert_registration_writable(
        incoming=registration(number="27aaapa1234a1zt"),
        existing=(),
        country_code="IN",
        state_tax_codes=INDIAN_STATES,
    )

    assert stored == "27AAAPA1234A1ZT"


def test_a_tax_system_the_jurisdiction_does_not_offer_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(tax_system="vat_gb"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"tax_system": "not offered in IN"}


def test_an_unknown_regime_is_refused() -> None:
    """``regime`` decides whether tax may be charged at all, so an unrecognized value is
    a registration no posting path could interpret."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(regime="flat_rate"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"regime": "not a gst_in regime"}


def test_a_jurisdiction_code_that_is_not_a_state_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(jurisdiction_code="ZZ"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"jurisdiction_code": "not a state of IN"}


def test_a_backwards_validity_window_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(valid_from=OCTOBER, valid_to=APRIL),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"valid_to": "earlier than valid_from"}


def test_a_malformed_gstin_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(number="27AAAPA1234A1X5"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"number": "does not match the gst_in format"}


def test_a_new_registration_that_overlaps_an_open_ended_one_is_refused() -> None:
    """The most common real mistake: adding the new registration without closing the old
    one. It is caught here rather than by a constraint because no DDL can express "no two
    rows with intersecting date ranges"."""
    with pytest.raises(ConflictError) as raised:
        assert_registration_writable(
            incoming=registration(number="27AAAPA1234A2ZS", valid_from=OCTOBER),
            existing=(registration(valid_to=None),),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert "Close the earlier one" in str(raised.value)


def test_a_new_registration_starting_the_day_after_the_old_one_ends_passes() -> None:
    """The correct way to record a regime change, and the reason the refusal above names
    the fix."""
    stored = assert_registration_writable(
        incoming=registration(number="27AAAPA1234A2ZS", valid_from=OCTOBER),
        existing=(registration(regime="composition", valid_to=SEPTEMBER_30),),
        country_code="IN",
        state_tax_codes=INDIAN_STATES,
    )

    assert stored == "27AAAPA1234A2ZS"


def test_an_amendment_is_not_compared_against_itself() -> None:
    """``existing`` is the company's **other** registrations. If the caller left the row
    being edited in, every amendment would be found to overlap itself and no registration
    could ever be corrected."""
    stored = assert_registration_writable(
        incoming=registration(valid_to=SEPTEMBER_30),
        existing=(),
        country_code="IN",
        state_tax_codes=INDIAN_STATES,
    )

    assert stored == "27AAAPA1234A1ZT"


def test_a_registration_in_another_state_does_not_overlap() -> None:
    """India issues one GSTIN per state and a company may hold several at once."""
    stored = assert_registration_writable(
        incoming=registration(jurisdiction_code="KA", number="29AAAPA1234A1ZP"),
        existing=(registration(jurisdiction_code="MH", valid_to=None),),
        country_code="IN",
        state_tax_codes=INDIAN_STATES,
    )

    assert stored == "29AAAPA1234A1ZP"


def test_the_checks_run_in_an_order_that_reports_the_most_fundamental_problem() -> None:
    """A row wrong in several ways should report the tax system rather than the number:
    the number format is *derived* from the tax system, so complaining about the number
    first would send the user to fix the wrong field."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(tax_system="vat_gb", number="nonsense"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert "tax_system" in raised.value.extra["fields"]


def test_a_uk_registration_passes_with_no_number_pattern() -> None:
    """A UK VAT number has several legitimate shapes, so the profile declares no pattern
    — and the composed check must still normalize and return it."""
    stored = assert_registration_writable(
        incoming=registration(
            tax_system="vat_gb",
            regime="standard",
            jurisdiction_code="GB",
            number="gb 123 4567 89",
        ),
        existing=(),
        country_code="GB",
        state_tax_codes={},
    )

    assert stored == "GB123456789"


def test_a_gstin_with_a_wrong_check_character_is_refused() -> None:
    """Regression: the old pattern accepted any final character."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(number="27AAAPA1234A1Z5"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"number": "check character does not match"}


def test_a_gstin_from_another_state_is_refused() -> None:
    """A Karnataka GSTIN on a Maharashtra registration — valid checksum, wrong state."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(number="29AAAPA1234A1ZP", jurisdiction_code="MH"),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {
        "number": "state prefix 29 does not match the jurisdiction's GST state code 27"
    }


def test_a_state_without_a_gst_code_cannot_take_a_gstin() -> None:
    """Refused rather than stored with the prefix rule silently off."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(),
            existing=(),
            country_code="IN",
            state_tax_codes={"MH": None},
        )

    assert raised.value.extra["fields"] == {"jurisdiction_code": "has no gst_in state code"}


def test_a_tds_deductor_registration_may_run_beside_the_regular_one() -> None:
    """The TAN-based GSTIN is accepted for a deductor, and the two registrations are
    different classes so they do not overlap."""
    deductor = _gstin("27MUMA12345B1D")

    stored = assert_registration_writable(
        incoming=registration(regime="tds_deductor", number=deductor),
        existing=(registration(is_primary=True),),
        country_code="IN",
        state_tax_codes=INDIAN_STATES,
    )

    assert stored == deductor


@pytest.mark.parametrize(
    ("regime", "expected"),
    [
        ("regular", "supplier"),
        ("composition", "supplier"),
        ("isd", "isd"),
        ("tds_deductor", "tds_deductor"),
        ("ecommerce_operator", "tcs_collector"),
    ],
)
def test_the_stored_class_comes_from_the_regime_catalogue(regime: str, expected: str) -> None:
    assert registration_class_of(registration(regime=regime)) == expected


def test_an_ecommerce_tcs_registration_may_run_beside_the_regular_one() -> None:
    collector = _gstin("27AAAPA1234A1C")

    stored = assert_registration_writable(
        incoming=registration(regime="ecommerce_operator", number=collector),
        existing=(registration(is_primary=True),),
        country_code="IN",
        state_tax_codes=INDIAN_STATES,
    )

    assert stored == collector


def test_a_tan_based_gstin_is_refused_for_a_regular_registration() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_registration_writable(
            incoming=registration(number=_gstin("27MUMA12345B1D")),
            existing=(),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )

    assert raised.value.extra["fields"] == {"number": "does not match the gst_in format"}


def test_two_regular_registrations_in_one_state_still_overlap() -> None:
    with pytest.raises(ConflictError):
        assert_registration_writable(
            incoming=registration(number="27AAAPA1234A2ZS", regime="composition"),
            existing=(registration(),),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )


def test_a_second_primary_is_refused_on_create() -> None:
    with pytest.raises(ConflictError):
        assert_registration_writable(
            incoming=registration(
                regime="tds_deductor", number=_gstin("27MUMA12345B1D"), is_primary=True
            ),
            existing=(registration(is_primary=True),),
            country_code="IN",
            state_tax_codes=INDIAN_STATES,
        )


# --- licences -----------------------------------------------------------------


def test_a_valid_licence_passes() -> None:
    assert_licence_writable(incoming=licence(), country_code="IN")


def test_a_licence_that_expires_must_carry_its_expiry_date() -> None:
    """**The gate would otherwise be decoration.** Left open-ended, the row satisfies
    every posting gate forever, which is exactly the failure ``renewal_reminder_days``
    and the Beat sweep exist to prevent."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_licence_writable(incoming=licence(valid_to=None), country_code="IN")

    assert raised.value.extra["fields"] == {
        "valid_to": "required for a bounded licence verification window"
    }


def test_every_indian_licence_kind_requires_an_expiry() -> None:
    """Asserted across the profile rather than for one kind, so a new licence kind added
    without ``has_expiry`` is caught by the pairing test in
    `libs/platform/tests/test_jurisdiction.py` and by this one together."""
    for kind in ("drug_licence_20b", "drug_licence_21b", "narcotic_licence", "fssai", "lut"):
        with pytest.raises(ValidationFailedError):
            assert_licence_writable(incoming=licence(kind=kind, valid_to=None), country_code="IN")


def test_a_backwards_licence_window_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_licence_writable(
            incoming=licence(valid_from=OCTOBER, valid_to=APRIL), country_code="IN"
        )

    assert raised.value.extra["fields"] == {"valid_to": "earlier than valid_from"}


def test_a_licence_with_a_blank_number_is_refused() -> None:
    """The number is legally required on the invoice, so a licence without one cannot do
    the job the row exists for."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_licence_writable(incoming=licence(number="   "), country_code="IN")

    assert raised.value.extra["fields"] == {"number": "empty"}


def test_a_licence_kind_the_jurisdiction_does_not_know_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_licence_writable(incoming=licence(kind="liquor_licence"), country_code="IN")

    assert raised.value.extra["fields"] == {"kind": "not a licence kind in IN"}


def test_no_licence_can_be_written_in_a_jurisdiction_that_declares_none() -> None:
    """The UK profile has no licences, so there is nothing to write there yet — refused
    rather than accepted as free text, which would be a row that gates nothing."""
    with pytest.raises(ValidationFailedError):
        assert_licence_writable(incoming=licence(), country_code="GB")


# --- neither is a permission ---------------------------------------------------


def test_no_write_rule_takes_an_actor_or_an_override() -> None:
    """None of these is a permission: ``tax_system`` immutability and overlap rejection
    hold for every actor including platform admin, because both protect documents that
    have already been filed."""
    forbidden = {"actor", "actor_user_id", "user", "force", "override", "is_platform_admin"}

    for function in (
        registration_changes,
        assert_registration_writable,
        assert_registration_coexists,
        assert_single_primary,
        assert_licence_writable,
    ):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & forbidden, f"{function.__name__} gained an override parameter"


def test_no_write_rule_touches_a_session() -> None:
    """CLAUDE.md §4: ``existing`` and ``state_tax_codes`` are passed in because the caller has
    already loaded them under its own tenant filter. A rule that issued its own query
    would be a second data path with no tenant scope of its own."""
    forbidden = {"session", "db", "connection", "engine", "company_id"}

    for function in (
        registration_changes,
        assert_registration_writable,
        assert_registration_coexists,
        assert_single_primary,
        assert_licence_writable,
    ):
        assert not set(inspect.signature(function).parameters) & forbidden
