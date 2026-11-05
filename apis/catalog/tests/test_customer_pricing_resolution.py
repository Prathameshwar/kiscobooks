"""Pure customer-pricing resolution chain — no database.

Every branch is a small dataclass wiring; the resolver returns a chain naming
the precedence step that won or refuses with a reason.
"""

import datetime as dt
import uuid

import pytest
from billing_platform.ids import uuid7

from catalog.domain.customer_pricing_resolution import (
    Assignment,
    CustomerPricingUnavailableError,
    PartyMembership,
    Resolution,
    resolve,
)


def _resolve(**overrides: object) -> Resolution:
    defaults: dict[str, object] = {
        "party_id": uuid7(),
        "posting_date": dt.date(2026, 6, 1),
        "memberships": (),
        "assignments": (),
        "company_default_price_level_id": None,
    }
    return resolve(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_party_assignment_wins_over_type_and_company() -> None:
    party = uuid7()
    party_level = uuid7()
    type_level = uuid7()
    default = uuid7()
    memberships = (PartyMembership(party, "WHOLESALE", dt.date(2026, 1, 1), None, True),)
    assignments = (
        Assignment("CUSTOMER", party, None, party_level, dt.date(2026, 1, 1), None),
        Assignment("PRICING_TYPE", None, "WHOLESALE", type_level, dt.date(2026, 1, 1), None),
    )
    result = _resolve(
        party_id=party,
        memberships=memberships,
        assignments=assignments,
        company_default_price_level_id=default,
    )
    assert result.price_level_id == party_level
    assert result.chain[0] == "party"


def test_customer_type_wins_when_no_party_assignment() -> None:
    party = uuid7()
    type_level = uuid7()
    default = uuid7()
    memberships = (PartyMembership(party, "WHOLESALE", dt.date(2026, 1, 1), None, True),)
    assignments = (
        Assignment("PRICING_TYPE", None, "WHOLESALE", type_level, dt.date(2026, 1, 1), None),
    )
    result = _resolve(
        party_id=party,
        memberships=memberships,
        assignments=assignments,
        company_default_price_level_id=default,
    )
    assert result.price_level_id == type_level
    assert result.chain == ("customer_type", "WHOLESALE")


def test_company_default_when_nothing_else_matches() -> None:
    party = uuid7()
    default = uuid7()
    result = _resolve(party_id=party, company_default_price_level_id=default)
    assert result.price_level_id == default
    assert result.chain == ("company", "default")


def test_missing_default_is_refused_not_silently_fallen_back() -> None:
    with pytest.raises(CustomerPricingUnavailableError, match="no company default"):
        _resolve()


def test_inactive_membership_does_not_pick_a_type() -> None:
    party = uuid7()
    default = uuid7()
    memberships = (PartyMembership(party, "WHOLESALE", dt.date(2026, 1, 1), None, is_active=False),)
    assignments = (
        Assignment("PRICING_TYPE", None, "WHOLESALE", uuid7(), dt.date(2026, 1, 1), None),
    )
    result = _resolve(
        party_id=party,
        memberships=memberships,
        assignments=assignments,
        company_default_price_level_id=default,
    )
    assert result.chain == ("company", "default")


def test_assignment_out_of_window_is_ignored() -> None:
    party = uuid7()
    default = uuid7()
    memberships = (PartyMembership(party, "WHOLESALE", dt.date(2026, 1, 1), None, True),)
    assignments = (
        # Both windows expire before the posting date.
        Assignment("CUSTOMER", party, None, uuid7(), dt.date(2026, 1, 1), dt.date(2026, 3, 31)),
        Assignment(
            "PRICING_TYPE", None, "WHOLESALE", uuid7(), dt.date(2026, 1, 1), dt.date(2026, 3, 31)
        ),
    )
    result = _resolve(
        party_id=party,
        memberships=memberships,
        assignments=assignments,
        company_default_price_level_id=default,
    )
    assert result.chain == ("company", "default")


def test_ambiguous_memberships_are_refused() -> None:
    party = uuid7()
    memberships = (
        PartyMembership(party, "RETAIL", dt.date(2026, 1, 1), None, True),
        PartyMembership(party, "WHOLESALE", dt.date(2026, 1, 1), None, True),
    )
    with pytest.raises(CustomerPricingUnavailableError, match="more than one active"):
        _resolve(party_id=party, memberships=memberships, company_default_price_level_id=uuid7())


def test_party_matches_but_type_absent_still_uses_default() -> None:
    party = uuid7()
    default = uuid7()
    # Party has no customer type; no CUSTOMER assignment either — fall through.
    memberships = (PartyMembership(party, None, dt.date(2026, 1, 1), None, True),)
    result = _resolve(
        party_id=party, memberships=memberships, company_default_price_level_id=default
    )
    assert result.chain == ("company", "default")


def test_returns_a_uuid_typed_price_level_not_a_string() -> None:
    party = uuid7()
    default = uuid7()
    result = _resolve(party_id=party, company_default_price_level_id=default)
    assert isinstance(result.price_level_id, uuid.UUID)


def test_overlapping_direct_assignments_fail_instead_of_using_query_order() -> None:
    party = uuid7()
    assignments = tuple(
        Assignment("CUSTOMER", party, None, uuid7(), dt.date(2026, 1, 1), None)
        for _ in range(2)
    )
    with pytest.raises(CustomerPricingUnavailableError, match="overlapping"):
        _resolve(party_id=party, assignments=assignments, company_default_price_level_id=uuid7())


def test_overlapping_type_assignments_fail_instead_of_using_query_order() -> None:
    party = uuid7()
    memberships = (PartyMembership(party, "WHOLESALE", dt.date(2026, 1, 1), None, True),)
    assignments = tuple(
        Assignment("PRICING_TYPE", None, "WHOLESALE", uuid7(), dt.date(2026, 1, 1), None)
        for _ in range(2)
    )
    with pytest.raises(CustomerPricingUnavailableError, match="overlapping"):
        _resolve(
            party_id=party, memberships=memberships,
            assignments=assignments, company_default_price_level_id=uuid7(),
        )
