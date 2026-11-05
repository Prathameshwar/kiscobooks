"""Company rules that come from the jurisdiction profile — no database at all.

Three rules, and each one is refusing something a permission cannot re-permit.

The cash ceiling is **lowerable, never raisable**, and ``None`` is the case worth
staring at: it means *no limit*, so where the jurisdiction has a ceiling it is the
largest possible raise — and it is exactly what a form that omitted the field would
send.

``assert_statutory_row_storable`` is deliberately redundant with
``plan_statutory_id``. The redundancy is the point: it catches a caller that built the
row some other way, and a full AADHAAR reaching the table is a legal exposure rather
than a bug to be found in review later.

``assert_jurisdiction_code_allowed`` is the check that stands in for the foreign key
``company_tax_registration.jurisdiction_code`` cannot have.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from identity.domain import (
    assert_cash_receipt_limit_allowed,
    assert_jurisdiction_code_allowed,
    assert_required_statutory_ids_present,
    assert_statutory_row_storable,
    plan_statutory_id,
)

INDIAN_STATES = frozenset({"MH", "KA", "TN", "DL"})

# --- the cash ceiling ---------------------------------------------------------


def test_the_statutory_ceiling_itself_is_allowed() -> None:
    """§269ST caps a cash receipt at ₹2,00,000, and a company may sit exactly on it."""
    assert_cash_receipt_limit_allowed(country_code="IN", cash_receipt_limit=Decimal("200000.0000"))


def test_a_stricter_house_rule_is_allowed() -> None:
    assert_cash_receipt_limit_allowed(country_code="IN", cash_receipt_limit=Decimal("50000.0000"))


def test_a_limit_above_the_statutory_ceiling_is_refused() -> None:
    """The ceiling is not the platform's policy — it is the law, and ``payments``
    enforcing a higher number would be helping a company break it."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_cash_receipt_limit_allowed(
            country_code="IN", cash_receipt_limit=Decimal("200000.0001")
        )

    assert raised.value.extra["fields"] == {
        "cash_receipt_limit": "above the IN statutory ceiling 200000.0000"
    }


def test_one_paisa_over_the_ceiling_is_still_over_it() -> None:
    """The comparison is on ``Decimal``, so the fourth decimal place is real. A float
    comparison would round it away and admit the raise."""
    with pytest.raises(ValidationFailedError):
        assert_cash_receipt_limit_allowed(
            country_code="IN", cash_receipt_limit=Decimal("200000.00005")
        )


def test_no_limit_at_all_is_refused_where_a_ceiling_exists() -> None:
    """**The one that a naive implementation gets wrong.** ``None`` means *unlimited*,
    which is the largest possible raise, and it is what a form omitting the field
    sends."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_cash_receipt_limit_allowed(country_code="IN", cash_receipt_limit=None)

    assert raised.value.extra["fields"] == {
        "cash_receipt_limit": "required in IN, at most 200000.0000"
    }


def test_no_limit_is_the_tenants_own_choice_where_no_ceiling_exists() -> None:
    """The UK has no statutory cash ceiling, so "unlimited" is a commercial decision and
    the platform has no basis to refuse it."""
    assert_cash_receipt_limit_allowed(country_code="GB", cash_receipt_limit=None)
    assert_cash_receipt_limit_allowed(country_code="GB", cash_receipt_limit=Decimal("9999999.0000"))


def test_an_unsupported_country_has_no_cash_rule_to_check() -> None:
    """It is refused at the profile lookup instead, which is the same answer arrived at
    earlier."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_cash_receipt_limit_allowed(country_code="FR", cash_receipt_limit=None)

    assert raised.value.extra["fields"] == {"country_code": "not a supported jurisdiction"}


# --- required identifiers -----------------------------------------------------


def test_a_company_holding_its_required_identifier_passes() -> None:
    assert_required_statutory_ids_present(country_code="IN", kinds={"pan", "tan"})


def test_a_company_missing_its_required_identifier_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_required_statutory_ids_present(country_code="IN", kinds={"tan", "cin"})

    assert raised.value.extra["fields"] == {"pan": "required in this jurisdiction"}
    assert "PAN" in str(raised.value)


def test_a_company_holding_nothing_is_refused() -> None:
    with pytest.raises(ValidationFailedError):
        assert_required_statutory_ids_present(country_code="IN", kinds=())


def test_the_check_is_against_what_the_company_holds_not_a_payload() -> None:
    """Identifiers arrive as separate rows over time, so the only meaningful question is
    what exists now — a Companies-House number satisfies the UK and would not satisfy
    India."""
    assert_required_statutory_ids_present(country_code="GB", kinds={"company_number"})

    with pytest.raises(ValidationFailedError):
        assert_required_statutory_ids_present(country_code="IN", kinds={"company_number"})


def test_an_unrelated_identifier_does_not_satisfy_the_requirement() -> None:
    with pytest.raises(ValidationFailedError):
        assert_required_statutory_ids_present(country_code="IN", kinds={"aadhaar"})


# --- planning and storing a value ---------------------------------------------


def test_planning_a_restricted_value_returns_only_its_last_four() -> None:
    """A thin pass-through to ``prepare_statutory_value`` on purpose: the discard has to
    live in ``libs/platform`` because every service accepting one must behave
    identically, and re-implementing it here is precisely the second code path
    CLAUDE.md §5.10 cannot survive."""
    stored = plan_statutory_id(country_code="IN", kind="aadhaar", value="1234 5678 9012")

    assert stored.value is None
    assert stored.value_last4 == "9012"


def test_planning_a_business_value_keeps_it_whole() -> None:
    stored = plan_statutory_id(country_code="IN", kind="pan", value="aaapa1234a")

    assert stored.value == "AAAPA1234A"
    assert stored.value_last4 == "234A"


def test_a_planned_value_is_storable_by_construction() -> None:
    """The two gates have to agree, or the second would reject rows the first produced.
    Asserted for both a restricted and an unrestricted kind."""
    for kind, submitted in (("aadhaar", "123456789012"), ("pan", "AAAPA1234A")):
        stored = plan_statutory_id(country_code="IN", kind=kind, value=submitted)
        assert_statutory_row_storable(
            country_code="IN",
            kind=kind,
            value=stored.value,
            value_last4=stored.value_last4,
        )


def test_a_restricted_row_carrying_a_full_value_is_refused_at_the_last_gate() -> None:
    """**The redundancy earning its place.** This is a caller that built the row without
    going through ``plan_statutory_id`` — the only way a full AADHAAR could reach the
    table, and the reason the check is repeated where the row is persisted."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_statutory_row_storable(
            country_code="IN", kind="aadhaar", value="123456789012", value_last4="9012"
        )

    assert raised.value.extra["fields"] == {"value": "must be absent for a restricted identifier"}


def test_the_refusal_does_not_echo_the_offending_value() -> None:
    """Echoing it is what put it at risk: the message travels into an error response and
    from there into whatever logs the client's failures."""
    full = "123456789012"

    with pytest.raises(ValidationFailedError) as raised:
        assert_statutory_row_storable(
            country_code="IN", kind="aadhaar", value=full, value_last4="9012"
        )

    assert full not in str(raised.value)
    assert full not in str(raised.value.extra)


def test_an_unrestricted_row_with_no_value_is_refused() -> None:
    """A PAN row holding only four characters is not a privacy measure, it is a lost
    identifier: it prints on invoices and cannot be reconstructed."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_statutory_row_storable(country_code="IN", kind="pan", value=None, value_last4="234A")

    assert raised.value.extra["fields"] == {"value": "required for an unrestricted identifier"}


def test_a_row_whose_last_four_are_not_four_characters_is_refused() -> None:
    """``value_last4`` is NOT NULL and four wide because it is the last column of the
    unique key. A short value would make that key compare things of different lengths."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_statutory_row_storable(
            country_code="IN", kind="pan", value="AAAPA1234A", value_last4="34A"
        )

    assert raised.value.extra["fields"] == {"value_last4": "not four characters"}


def test_a_row_whose_last_four_disagree_with_its_value_is_refused() -> None:
    """The two columns are derived from one input, so a disagreement means one of them
    was typed — and the unique key would then be enforcing uniqueness of the wrong
    thing."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_statutory_row_storable(
            country_code="IN", kind="pan", value="AAAPA1234A", value_last4="9999"
        )

    assert raised.value.extra["fields"] == {"value_last4": "inconsistent with value"}


def test_an_unknown_kind_cannot_be_stored() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_statutory_row_storable(
            country_code="IN", kind="ssn", value="123456789", value_last4="6789"
        )

    assert raised.value.extra["fields"] == {"kind": "not a statutory identifier in IN"}


# --- the jurisdiction code the missing foreign key cannot check ----------------


def test_an_indian_registration_must_name_a_state() -> None:
    assert_jurisdiction_code_allowed(
        country_code="IN", jurisdiction_code="MH", state_codes=INDIAN_STATES
    )


def test_an_indian_registration_naming_the_country_is_refused() -> None:
    """`IN` is not a GST jurisdiction — there is no all-India GSTIN — and accepting it
    would put a registration in force for every state at once."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_jurisdiction_code_allowed(
            country_code="IN", jurisdiction_code="IN", state_codes=INDIAN_STATES
        )

    assert raised.value.extra["fields"] == {"jurisdiction_code": "not a state of IN"}


def test_an_indian_registration_naming_a_foreign_state_is_refused() -> None:
    """The caller passes the country's own subdivisions, so a code from elsewhere is not
    in the set — this is the check that replaces the absent foreign key."""
    with pytest.raises(ValidationFailedError):
        assert_jurisdiction_code_allowed(
            country_code="IN", jurisdiction_code="CA", state_codes=INDIAN_STATES
        )


def test_a_uk_registration_must_name_the_country() -> None:
    """One VAT number for the country, so `GB` is the only allowed value — and the same
    column holds a state code in India, which is why no single FK target exists."""
    assert_jurisdiction_code_allowed(country_code="GB", jurisdiction_code="GB", state_codes=())


def test_a_uk_registration_naming_a_subdivision_is_refused() -> None:
    """`SCT` is a real ISO subdivision of the UK and not a VAT jurisdiction. Accepting it
    would create four registrations where one exists."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_jurisdiction_code_allowed(
            country_code="GB", jurisdiction_code="SCT", state_codes={"SCT", "WLS", "ENG", "NIR"}
        )

    assert raised.value.extra["fields"] == {"jurisdiction_code": "expected GB"}


def test_an_empty_state_set_refuses_every_indian_code() -> None:
    """Fails closed. A caller that forgot to load the subdivisions gets a refusal rather
    than an unchecked write, which is the failure mode the missing FK would otherwise
    have."""
    with pytest.raises(ValidationFailedError):
        assert_jurisdiction_code_allowed(country_code="IN", jurisdiction_code="MH", state_codes=())


def test_an_unsupported_country_has_no_scope_to_check_against() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_jurisdiction_code_allowed(
            country_code="FR", jurisdiction_code="75", state_codes=("75",)
        )

    assert raised.value.extra["fields"] == {"country_code": "not a supported jurisdiction"}


# --- none of these is a permission --------------------------------------------


def test_no_jurisdiction_rule_takes_an_actor_or_an_override() -> None:
    """**Asserted structurally, because the AADHAAR rule is the one prohibition on this
    platform that no role can lift** — not platform admin, not the tenant owner. If
    someone adds ``actor`` or ``force`` to one of these signatures, it has become a
    permission and this fails."""
    forbidden = {"actor", "actor_user_id", "user", "force", "override", "is_platform_admin"}

    for function in (
        assert_cash_receipt_limit_allowed,
        assert_required_statutory_ids_present,
        plan_statutory_id,
        assert_statutory_row_storable,
        assert_jurisdiction_code_allowed,
    ):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & forbidden, f"{function.__name__} gained an override parameter"


def test_no_jurisdiction_rule_touches_a_session() -> None:
    """CLAUDE.md §4: ``domain/`` imports no framework and holds no session. ``state_codes``
    is passed in for exactly this reason — the caller has already loaded them under its
    own tenant filter."""
    forbidden = {"session", "db", "connection", "engine"}

    for function in (
        assert_cash_receipt_limit_allowed,
        assert_required_statutory_ids_present,
        plan_statutory_id,
        assert_statutory_row_storable,
        assert_jurisdiction_code_allowed,
    ):
        assert not set(inspect.signature(function).parameters) & forbidden
