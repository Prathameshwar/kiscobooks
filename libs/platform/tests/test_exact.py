from decimal import Context, Decimal, Inexact, localcontext
from fractions import Fraction
from typing import Any

import pytest

from billing_platform.exact import (
    RationalConversion,
    convert_quantity,
    exact_decimal,
    per_unit_ratio,
)
from billing_platform.money import MoneyError


@pytest.mark.parametrize("value", ["1.23000", Decimal("1.23"), 12, "-1.23", "0"])
def test_exact_values_survive_storage(value: Any) -> None:
    result = exact_decimal(value, decimal_places=2)
    assert isinstance(result, Decimal)
    assert result == Decimal(value)
    assert result.as_tuple().exponent == -4


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        1.5,
        None,
        [],
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        "bad",
        "1" * 129,
        "1000000000000000",
        "-1000000000000000",
        "0.00001",
        "1e-999999",
    ],
)
def test_invalid_entries_never_silently_round(value: Any) -> None:
    with pytest.raises(MoneyError):
        exact_decimal(value)


@pytest.mark.parametrize("places", [-1, 5, True, 1.5])
def test_precision_is_a_bounded_integer(places: Any) -> None:
    with pytest.raises(MoneyError):
        exact_decimal("1", decimal_places=places)


@pytest.mark.parametrize("step", ["0", "-0.01", "0.001", "NaN"])
def test_invalid_increment(step: str) -> None:
    with pytest.raises(MoneyError):
        exact_decimal("1.00", decimal_places=2, increment=step)


def test_increment_and_serialized_quantity() -> None:
    assert exact_decimal("1.25", decimal_places=2, increment="0.05") == Decimal("1.25")
    with pytest.raises(MoneyError):
        exact_decimal("1.23", decimal_places=2, increment="0.05")
    with pytest.raises(MoneyError):
        exact_decimal("1.5", decimal_places=0)
    assert exact_decimal("-2.00", decimal_places=0) == -2


@pytest.mark.parametrize("n,d", [(0, 1), (1, 0), (-1, 2), (True, 2), (1, 2**63)])
def test_invalid_conversion(n: Any, d: Any) -> None:
    with pytest.raises(MoneyError):
        RationalConversion(n, d)


def test_conversion_preserves_pack_and_fraction_requirements() -> None:
    boxes = RationalConversion(24, 2)
    assert (boxes.numerator, boxes.denominator) == (12, 1)
    assert convert_quantity("2.5", boxes, decimal_places=0) == Decimal("30")
    assert convert_quantity("30", boxes.inverse(), increment="0.5") == Decimal("2.5")
    thirds = RationalConversion(1, 3)
    assert thirds.apply("1") == Fraction(1, 3)
    with pytest.raises(MoneyError):
        convert_quantity("1", thirds)
    with pytest.raises(MoneyError):
        convert_quantity("0.5", RationalConversion(1, 1), decimal_places=0)
    with pytest.raises(MoneyError):
        convert_quantity("999999999999999", RationalConversion(2, 1))


def test_rate_basis_is_not_rounded_into_per_unit_price() -> None:
    assert per_unit_ratio("0.01", "1000") == Fraction(1, 100_000)
    assert per_unit_ratio("1", "3") * 3 == 1
    for basis in ("0", "-1", "0.00001"):
        with pytest.raises(MoneyError):
            per_unit_ratio("1", basis)


def test_caller_decimal_context_does_not_change_entry_rules() -> None:
    with localcontext(Context(prec=2)) as context:
        context.traps[Inexact] = True
        assert exact_decimal("999999999999999.9999") == Decimal("999999999999999.9999")
        assert convert_quantity("-0.25", RationalConversion(1000, 1)) == Decimal("-250")
        with pytest.raises(MoneyError):
            exact_decimal("1.234", decimal_places=2)
