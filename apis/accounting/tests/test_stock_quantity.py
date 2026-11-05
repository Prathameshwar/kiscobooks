"""Exact native conversion/measurement evidence and mismatched-base rejection."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode
from voucher_execution.quantity import QuantityUnitFact
from voucher_execution.stock import StockLine

from accounting.domain.stock_opening import calculate
from accounting.domain.stock_quantity import validate_capture


def evidence(mode="FIXED", **changes):
    item, unit, revision = uuid7(), uuid7(), uuid7()
    fact = QuantityUnitFact(
        item_id=item,
        unit_id=unit,
        revision_id=revision,
        usage_role="MEASURED" if mode == "MEASURED" else "PACK",
        conversion_mode=mode,
        numerator=None if mode == "MEASURED" else "12",
        denominator=None if mode == "MEASURED" else "1",
        quantity_increment="0.001",
        quantity_decimal_places=3,
        fractional_entry=True,
    )
    profile = SimpleNamespace(
        quantity_units=[fact],
        quantity_increment="1",
        quantity_decimal_places=0,
        serial_tracking=False,
    )
    line = StockLine(
        line_id=uuid7(),
        item_id=item,
        warehouse_id=uuid7(),
        quantity="24",
        quantity_entry={
            "entered_unit_id": unit,
            "unit_revision_id": revision,
            "entered_quantity": "2",
            **changes,
        },
    )
    return line, profile


def test_fixed_entry_conserves_exact_base_quantity():
    line, item = evidence()
    validate_capture(line, item, "RECEIPT")
    with pytest.raises(ValidationFailedError, match="do not agree"):
        validate_capture(line.model_copy(update={"quantity": line.quantity + 1}), item, "RECEIPT")


def test_actual_measurement_is_required_and_nominal_ratio_is_absent():
    line, item = evidence("MEASURED")
    with pytest.raises(ValidationFailedError, match="actual base"):
        validate_capture(line, item, "RECEIPT")
    line, item = evidence("MEASURED", measured_base_quantity="24")
    validate_capture(line, item, "RECEIPT")
    with pytest.raises(ValidationFailedError, match="do not agree"):
        validate_capture(line.model_copy(update={"quantity": line.quantity + 1}), item, "RECEIPT")


def test_fixed_quantity_rejects_measured_override_and_untrusted_revision():
    line, item = evidence(measured_base_quantity="24")
    with pytest.raises(ValidationFailedError, match="override"):
        validate_capture(line, item, "TRANSFER")
    item.quantity_units = []
    with pytest.raises(ConflictError, match="unavailable"):
        validate_capture(line, item, "TRANSFER")


def test_large_ratio_parts_are_never_rounded_to_javascript_numbers():
    line, item = evidence()
    item.quantity_units[0] = item.quantity_units[0].model_copy(
        update={"numerator": "9007199254740993", "denominator": "9007199254740995"}
    )
    with pytest.raises(ValidationFailedError, match="do not agree"):
        validate_capture(line, item, "DISPATCH")


def test_measured_opening_uses_actual_base_measurement_and_entered_unit_rate():
    result = calculate(
        entered_quantity=Decimal("2"),
        numerator=None,
        denominator=None,
        entered_increment=Decimal("1"),
        base_increment=Decimal("0.001"),
        entered_places=0,
        base_places=3,
        serialized=False,
        cost_mode="RATE",
        unit_cost=Decimal("100"),
        priced_quantity=Decimal("1"),
        received_value=None,
        places=2,
        rounding=RoundingMode.HALF_UP,
        conversion_mode="MEASURED",
        measured_base_quantity=Decimal("23.456"),
    )
    assert result.base_quantity == Decimal("23.456")
    assert result.value == Decimal("200")
