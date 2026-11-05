"""Opening arithmetic has no stock side effects and never guesses missing value."""

from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.money import RoundingMode

from accounting.domain.stock_opening import calculate


def value(**changes):
    return calculate(
        **{
            "entered_quantity": Decimal("2"),
            "numerator": 12,
            "denominator": 1,
            "entered_increment": Decimal("1"),
            "base_increment": Decimal("1"),
            "entered_places": 0,
            "base_places": 0,
            "serialized": False,
            "cost_mode": "RATE",
            "unit_cost": Decimal("120.005"),
            "priced_quantity": Decimal("1"),
            "received_value": None,
            "places": 2,
            "rounding": RoundingMode.HALF_UP,
            **changes,
        }
    )


def test_entered_unit_rate_and_value_are_exact():
    result = value()
    assert result.base_quantity == Decimal("24")
    assert result.value == Decimal("240.01")
    assert result.derived_unit_cost == Decimal("120.0050")
    assert result.derived_base_unit_cost == Decimal("10.0004")


def test_value_mode_keeps_total_authoritative_and_reports_derived_rate():
    result = value(cost_mode="VALUE", unit_cost=None, received_value=Decimal("100"))
    assert result.value == Decimal("100")
    assert result.derived_unit_cost == Decimal("50")
    assert result.derived_base_unit_cost == Decimal("4.1667")


@pytest.mark.parametrize(
    "changes",
    [
        {"entered_quantity": Decimal("-1")},
        {"entered_quantity": Decimal("0")},
        {"entered_quantity": Decimal("1.00001")},
        {"entered_quantity": Decimal("NaN")},
        {"entered_quantity": 2},
        {"numerator": 0},
        {"denominator": 0},
        {"numerator": True},
        {"priced_quantity": Decimal("0")},
        {"unit_cost": None},
        {"received_value": Decimal("240")},
        {"numerator": 1, "denominator": 3, "base_places": 4},
        {"entered_quantity": Decimal("1.5")},
        {"base_increment": Decimal("5")},
        {
            "entered_quantity": Decimal("1"),
            "numerator": 1,
            "denominator": 2,
            "base_increment": Decimal("0.5"),
            "serialized": True,
            "base_places": 4,
        },
        {"cost_mode": "VALUE", "unit_cost": None},
        {"cost_mode": "VALUE", "received_value": Decimal("100")},
        {"unit_cost": Decimal("999999999999999.9999")},
    ],
)
def test_invalid_or_unrepresentable_input_is_rejected(changes):
    with pytest.raises(ValidationFailedError):
        value(**changes)


def test_explicit_zero_is_distinct_from_missing_value():
    assert value(unit_cost=Decimal("0")).value == Decimal("0")
    assert value(cost_mode="VALUE", unit_cost=None, received_value=Decimal("0")).value == 0


def test_rational_conversion_is_exact_without_intermediate_rounding():
    assert value(
        numerator=1, denominator=8, base_places=4, base_increment=Decimal("0.0001")
    ).base_quantity == Decimal("0.25")
