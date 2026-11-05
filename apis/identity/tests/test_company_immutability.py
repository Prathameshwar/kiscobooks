"""The freeze on a company's shape after its first posting — invariant 16.

No database, no session, no app (CLAUDE.md §7: "domain rules tested with no database
at all"). Two things carry most of the weight here:

* **the diff, not the payload** — a client PUTting an unchanged company back is not
  editing anything, and rejecting on presence would make every full update
  impossible after the first posting;
* **no actor parameter** — the last test in this file asserts the signatures, because
  the moment an override argument appears the rule has silently become a permission.
"""

from __future__ import annotations

import datetime as dt
import inspect

import pytest
from billing_platform.errors import ImmutableFieldError

from identity.domain import (
    IMMUTABLE_AFTER_POSTING,
    assert_company_fields_mutable,
    assert_update_allowed,
    changed_fields,
)

#: A company that has posted. Any timestamp will do — the rule reads "is it set",
#: never "how long ago", because a document filed yesterday is as filed as one from
#: five years ago.
POSTED = dt.datetime(2026, 5, 1, 8, 0, tzinfo=dt.UTC)

CURRENT = {
    "code": "MAIN",
    "legal_name": "Acme Traders Private Limited",
    "display_name": "Acme Traders",
    "base_currency": "INR",
    "country_code": "IN",
    "state_code": "MH",
    "fiscal_year_start_month": 4,
    "fiscal_year_start_day": 1,
    "books_begin_date": dt.date(2026, 4, 1),
    "amount_precision": 2,
    "quantity_precision": 3,
    "rounding_mode": "half_up",
    "default_payment_terms_days": 30,
}

#: A different, individually valid value for each frozen field — so a test can change
#: one without inventing a value inline and accidentally reusing the current one.
OTHER_VALUE = {
    "code": "HEAD",
    "base_currency": "USD",
    "country_code": "GB",
    "state_code": "ENG",
    "fiscal_year_start_month": 1,
    "fiscal_year_start_day": 15,
    "books_begin_date": dt.date(2025, 4, 1),
    "amount_precision": 4,
    "quantity_precision": 2,
    "rounding_mode": "half_even",
}


# --- the documented set -------------------------------------------------------


def test_the_frozen_set_is_the_documented_one() -> None:
    """docs/company.md §5.2. Spelled out rather than derived, so adding a field to the
    module without deciding it belongs here fails."""
    assert IMMUTABLE_AFTER_POSTING == {
        "base_currency",
        "fiscal_year_start_month",
        "fiscal_year_start_day",
        "books_begin_date",
        "amount_precision",
        "quantity_precision",
        "rounding_mode",
        "code",
        "country_code",
        "state_code",
    }


def test_every_frozen_field_has_a_test_value() -> None:
    """Guards the two constants above against drifting apart — otherwise a new frozen
    field would be silently untested by the parametrised cases below."""
    assert set(OTHER_VALUE) == IMMUTABLE_AFTER_POSTING
    assert IMMUTABLE_AFTER_POSTING <= set(CURRENT)


# --- before the first posting -------------------------------------------------


def test_nothing_is_frozen_before_the_first_posting() -> None:
    """The whole set, at once. Setup is exactly when these are meant to be corrected —
    a company created with the wrong fiscal start must be fixable, not replaced."""
    assert_update_allowed(CURRENT, dict(OTHER_VALUE), first_posted_at=None)


@pytest.mark.parametrize("field", sorted(IMMUTABLE_AFTER_POSTING))
def test_each_field_is_editable_before_the_first_posting(field: str) -> None:
    assert_update_allowed(CURRENT, {field: OTHER_VALUE[field]}, first_posted_at=None)


# --- after the first posting ---------------------------------------------------


@pytest.mark.parametrize("field", sorted(IMMUTABLE_AFTER_POSTING))
def test_each_frozen_field_is_rejected_after_the_first_posting(field: str) -> None:
    """Each one individually, because a loop that stopped at the first failure would
    pass with nine of the ten unenforced."""
    with pytest.raises(ImmutableFieldError) as raised:
        assert_update_allowed(CURRENT, {field: OTHER_VALUE[field]}, first_posted_at=POSTED)

    assert raised.value.extra["fields"] == {field: "immutable after first posting"}


def test_a_mutable_field_is_still_editable_after_the_first_posting() -> None:
    """The freeze is ten columns, not the table. A trade name, a logo, a signatory —
    those change without touching any figure already filed."""
    assert_update_allowed(
        CURRENT,
        {"legal_name": "Acme Traders Limited", "default_payment_terms_days": 45},
        first_posted_at=POSTED,
    )


def test_every_frozen_field_is_named_in_one_refusal() -> None:
    """A caller changing several gets told about all of them at once, in a stable
    order. Reporting one at a time turns a single correction into ten round trips."""
    with pytest.raises(ImmutableFieldError) as raised:
        assert_update_allowed(CURRENT, dict(OTHER_VALUE), first_posted_at=POSTED)

    assert set(raised.value.extra["fields"]) == IMMUTABLE_AFTER_POSTING
    assert ", ".join(sorted(IMMUTABLE_AFTER_POSTING)) in str(raised.value)


def test_a_mixed_payload_names_only_the_frozen_fields() -> None:
    """The mutable half of the same request is not the reason it failed, and saying so
    would send someone looking in the wrong place."""
    with pytest.raises(ImmutableFieldError) as raised:
        assert_update_allowed(
            CURRENT,
            {"base_currency": "USD", "legal_name": "Acme Traders Limited"},
            first_posted_at=POSTED,
        )

    assert raised.value.extra["fields"] == {"base_currency": "immutable after first posting"}


def test_the_refusal_names_the_supported_route() -> None:
    """The answer is never "ask an admin" — it is a new company with migrated opening
    balances. An error that does not say so produces a support ticket asking for an
    override that must not exist."""
    with pytest.raises(ImmutableFieldError) as raised:
        assert_update_allowed(CURRENT, {"base_currency": "USD"}, first_posted_at=POSTED)

    message = str(raised.value)
    assert "posted documents" in message
    assert "opening balances" in message


# --- the diff, not the payload ------------------------------------------------


def test_resending_a_frozen_field_unchanged_is_allowed() -> None:
    """**The load-bearing case.** A full-object PUT round-trips every field, so
    rejecting on payload presence would make any full update impossible after the
    first posting — and clients would work around it with partial payloads, which is
    how a field ends up cleared by accident."""
    assert_update_allowed(CURRENT, dict(CURRENT), first_posted_at=POSTED)


def test_resending_the_whole_company_unchanged_changes_nothing() -> None:
    assert changed_fields(CURRENT, dict(CURRENT)) == frozenset()


def test_only_differing_values_count_as_changed() -> None:
    incoming = {"code": "MAIN", "legal_name": "Acme Traders Limited"}

    assert changed_fields(CURRENT, incoming) == {"legal_name"}


def test_a_field_absent_from_the_payload_is_untouched() -> None:
    """PATCH semantics: omission is "leave it alone", never "set it to null"."""
    assert changed_fields(CURRENT, {"legal_name": "Acme Traders Limited"}) == {"legal_name"}


def test_a_field_absent_from_current_counts_as_changed() -> None:
    """There is nothing to compare it against, so the safe reading is "changed". A
    field the caller invented must not slip past the freeze by being unknown."""
    assert changed_fields({}, {"base_currency": "INR"}) == {"base_currency"}


def test_a_type_change_with_an_equal_value_is_not_a_change() -> None:
    """``2 == 2.0`` in Python, and an int precision arriving as a float from JSON is
    not someone editing it. Money columns are guarded at the column type (a float
    raises on bind), so equality is the right test for these display scales."""
    assert changed_fields({"amount_precision": 2}, {"amount_precision": 2.0}) == frozenset()


# --- not a permission ---------------------------------------------------------


def test_the_freeze_takes_no_actor_and_no_override() -> None:
    """**Invariant 16's "for every actor" clause, asserted structurally.**

    If someone later adds ``actor``, ``force`` or ``is_platform_admin`` to one of
    these signatures, the rule has become a permission and this test fails. That is
    the only way to test "no role lifts it" without enumerating every role.
    """
    forbidden = {"actor", "actor_user_id", "user", "force", "override", "is_platform_admin"}

    for function in (assert_company_fields_mutable, assert_update_allowed, changed_fields):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & forbidden, f"{function.__name__} gained an override parameter"


def test_the_module_raises_a_422_not_a_403() -> None:
    """422 says "this value is not acceptable"; 403 says "not by you", which would
    invite someone to find an actor for whom it is. The status is the message."""
    with pytest.raises(ImmutableFieldError) as raised:
        assert_company_fields_mutable(["base_currency"], first_posted_at=POSTED)

    assert raised.value.status_code == 422


def test_an_empty_change_set_after_posting_is_fine() -> None:
    """Called on a no-op update, which routes do rather than special-casing."""
    assert_company_fields_mutable([], first_posted_at=POSTED)


def test_a_change_set_of_only_mutable_fields_after_posting_is_fine() -> None:
    assert_company_fields_mutable(["legal_name", "logo_url"], first_posted_at=POSTED)
