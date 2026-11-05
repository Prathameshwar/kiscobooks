"""BOM publication/preview grids never silently round physical quantities."""

from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.exact import RationalConversion
from billing_platform.ids import uuid7

from catalog.domain.bom_definitions import BatchRule, PhysicalQuantity
from catalog.domain.units import QuantityRule


def test_batch_rules_require_explicit_exact_run_breakdown():
    rule = BatchRule(Decimal("10"), Decimal("50"), Decimal("5"))
    rule.validate(Decimal("60"), 2, (Decimal("30"), Decimal("30")))
    for runs in (
        None,
        (Decimal("60"),),
        (Decimal("27"), Decimal("33")),
        (Decimal("30"), Decimal("25")),
    ):
        with pytest.raises(ValidationFailedError):
            rule.validate(Decimal("60"), 2, runs)


def test_batch_constraints_are_coherent_and_exact():
    for values in (("20", "10", "1"), ("0", "10", "1"), ("1", "10", "0"), ("1.00001", "10", "1")):
        with pytest.raises(ValidationFailedError):
            BatchRule(*(Decimal(value) for value in values))
    BatchRule().validate(Decimal("10"), None, None)
    with pytest.raises(ValidationFailedError):
        BatchRule().validate(Decimal("10"), None, (Decimal("10"),))


def test_physical_grid_validates_entered_conversion_and_serial_base():
    item = uuid7()
    rule = PhysicalQuantity(
        item,
        QuantityRule(2, Decimal("0.25")),
        QuantityRule(0, Decimal("1")),
        RationalConversion(4, 1),
        True,
    )
    assert rule.validate(Decimal("0.5")) == Decimal("2")
    for value in (Decimal("0.1"), Decimal("0.125"), Decimal("-1")):
        with pytest.raises(ValidationFailedError):
            rule.validate(value)


def test_serialized_base_rejects_fraction_after_exact_conversion():
    rule = PhysicalQuantity(
        uuid7(),
        QuantityRule(4, Decimal("0.0001")),
        QuantityRule(4, Decimal("0.0001")),
        RationalConversion(1, 2),
        True,
    )
    with pytest.raises(ValidationFailedError):
        rule.validate(Decimal("1"))


def test_batch_range_must_contain_a_permitted_positive_multiple():
    for minimum, maximum, multiple in (("5", "6", "10"), (None, "5", "10"), ("11", "11", "4")):
        with pytest.raises(ValidationFailedError):
            BatchRule(Decimal(minimum) if minimum else None, Decimal(maximum), Decimal(multiple))
    BatchRule(Decimal("9"), Decimal("10"), Decimal("3"))


def test_batch_validates_nominal_count_and_each_run_before_using_them():
    for nominal, count, runs in (
        (Decimal("0"), None, None),
        (Decimal("1.00001"), None, None),
        (Decimal("1"), True, None),
        (Decimal("1"), 1001, None),
        (Decimal("1"), 1, (Decimal("1.00001"),)),
    ):
        with pytest.raises(ValidationFailedError):
            BatchRule().validate(nominal, count, runs)
    rule = BatchRule(Decimal("10"), Decimal("50"), Decimal("5"))
    for runs in ((Decimal("55"), Decimal("5")), (Decimal("5"), Decimal("55"))):
        with pytest.raises(ValidationFailedError):
            rule.validate(Decimal("60"), 2, runs)


def test_fixed_unit_rejects_disabled_fractional_entry_and_repeating_base_quantities():
    grid = QuantityRule(4, Decimal("0.0001"))
    fractional = PhysicalQuantity(
        uuid7(), grid, grid, RationalConversion(1, 1), fractional_entry=False
    )
    with pytest.raises(ValidationFailedError):
        fractional.validate(Decimal("0.5"))
    repeating = PhysicalQuantity(uuid7(), grid, grid, RationalConversion(1, 3))
    with pytest.raises(ValidationFailedError):
        repeating.validate(Decimal("1"))
