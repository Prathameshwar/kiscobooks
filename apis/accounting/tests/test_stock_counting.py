"""Missing or ambiguous native cost requires an explicit reviewed decision."""

from decimal import Decimal
from fractions import Fraction

import pytest
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode

from accounting.domain.stock_costing import CostBucket
from accounting.domain.stock_counting import surplus_value, verified_cost


def bucket(quantity, value):
    return CostBucket(uuid7(), Decimal(quantity), Decimal(value))


def test_fifo_mixed_cost_is_reviewed_instead_of_guessing_a_layer():
    assert verified_cost("FIFO", bucket("4", "30"), [bucket("2", "10"), bucket("2", "20")]) is None
    assert verified_cost("FIFO", bucket("4", "20"), [bucket("2", "10"), bucket("2", "10")]) == 5


@pytest.mark.parametrize("pool", [None, bucket("0", "0")])
def test_missing_current_cost_is_never_assumed_zero(pool):
    assert verified_cost("MOVING_AVERAGE", pool, []) is None


def test_verified_zero_and_average_cost_are_retained_exactly():
    assert verified_cost("MOVING_AVERAGE", bucket("2", "0"), []) == 0
    assert verified_cost("MOVING_AVERAGE", bucket("3", "10"), []) == Fraction(10, 3)
    assert surplus_value(Decimal("2"), Fraction(10, 3), 2, RoundingMode.HALF_UP) == Decimal("6.67")
