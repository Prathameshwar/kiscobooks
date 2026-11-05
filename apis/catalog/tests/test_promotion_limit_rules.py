"""Limit identities retain quota meaning and caps retain exact native precision."""

from decimal import Decimal
from uuid import UUID

import pytest
from billing_platform.errors import ValidationFailedError

from catalog.domain.promotion_limits import LimitIdentity, validate_cap


def test_limit_counts_keep_signed_64_bit_precision():
    identity = LimitIdentity("PROGRAM", "TOTAL_USES", "LIFETIME", "Asia/Kolkata")
    assert validate_cap(identity, maximum_count=2**63 - 1) == 2**63 - 1
    for count in (True, 1.5, 0, -1, 2**63):
        with pytest.raises(ValidationFailedError):
            validate_cap(identity, maximum_count=count)


def test_limit_budget_and_reward_units_are_typed_and_exact():
    budget = LimitIdentity("CAMPAIGN", "BUDGET", "MONTH", "Asia/Kolkata", currency="INR")
    assert validate_cap(budget, maximum_amount=Decimal("1000.2500")) == Decimal("1000.2500")
    reward = LimitIdentity(
        "PROMOTION",
        "REWARD_UNITS",
        "DAY",
        "Asia/Kolkata",
        unit_id=UUID("01990000-0000-7000-8000-000000000001"),
    )
    assert validate_cap(reward, maximum_quantity=Decimal("25.0000")) == Decimal("25.0000")
    for values in (
        {"maximum_amount": 1.5},
        {"maximum_amount": Decimal("0")},
        {"maximum_amount": Decimal("1.00001")},
        {"maximum_count": 10},
        {"maximum_amount": Decimal("1"), "maximum_quantity": Decimal("1")},
    ):
        with pytest.raises(ValidationFailedError):
            validate_cap(budget, **values)


@pytest.mark.parametrize(
    "values",
    [
        ("COUPON", "TOTAL_USES", "LIFETIME", "UTC"),
        ("PROGRAM", "UNKNOWN", "LIFETIME", "UTC"),
        ("PROGRAM", "TOTAL_USES", "ORDER", "UTC"),
        ("PROGRAM", "PER_ORDER_USES", "MONTH", "UTC"),
        ("PROGRAM", "TOTAL_USES", "LIFETIME", "Unknown/Zone"),
    ],
)
def test_limit_scope_metric_period_and_timezone_are_native(values):
    with pytest.raises(ValidationFailedError):
        LimitIdentity(*values)


@pytest.mark.parametrize(
    "changes", [{"currency": "inr"}, {"currency": "US"}, {"currency": "12A"}, {"currency": "INRR"}]
)
def test_budget_currency_is_native(changes):
    with pytest.raises(ValidationFailedError):
        LimitIdentity("PROGRAM", "BUDGET", "LIFETIME", "UTC", **changes)


def test_limit_measure_contract_is_required_and_real():
    with pytest.raises(ValidationFailedError):
        LimitIdentity("PROGRAM", "BUDGET", "LIFETIME", "UTC")
    with pytest.raises(ValidationFailedError):
        LimitIdentity("PROGRAM", "REWARD_UNITS", "LIFETIME", "UTC", unit_id=UUID(int=0))
    with pytest.raises(ValidationFailedError):
        validate_cap(LimitIdentity("PROGRAM", "BUDGET", "LIFETIME", "UTC", currency="INR"))
    assert LimitIdentity("PROGRAM", "PER_ORDER_USES", "ORDER", "UTC").period_basis == "ORDER"
