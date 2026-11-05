"""Native entered/base agreement; nominal measured ratios never execute stock."""

from fractions import Fraction

from billing_platform.errors import ConflictError, ValidationFailedError
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact


def validate_capture(line: StockLine, item: StockItemFact, action: str) -> None:
    capture = line.quantity_entry
    if capture is None:
        return
    selected = [
        fact
        for fact in item.quantity_units
        if fact.revision_id == capture.unit_revision_id
        and fact.unit_id == capture.entered_unit_id
        and fact.item_id == line.item_id
    ]
    if len(selected) != 1:
        raise ConflictError("entered quantity unit evidence is unavailable or changed")
    fact = selected[0]
    if action in {"RECEIPT", "SUPPLIER_RETURN"} and fact.usage_role == "SALE":
        raise ConflictError("entered quantity unit is not enabled for purchases")
    if action in {"DISPATCH", "CUSTOMER_RETURN"} and fact.usage_role == "PURCHASE":
        raise ConflictError("entered quantity unit is not enabled for sales")
    entered = Fraction(capture.entered_quantity)
    if (
        (entered * 10**fact.quantity_decimal_places).denominator != 1
        or (entered / Fraction(fact.quantity_increment)).denominator != 1
        or (not fact.fractional_entry and entered.denominator != 1)
    ):
        raise ValidationFailedError("entered quantity violates its product unit grid")
    if fact.conversion_mode == "FIXED":
        if capture.measured_base_quantity is not None:
            raise ValidationFailedError("fixed quantities cannot accept a measured override")
        assert fact.numerator is not None and fact.denominator is not None
        base = entered * Fraction(int(fact.numerator), int(fact.denominator))
    else:
        if capture.measured_base_quantity is None:
            raise ValidationFailedError("measured entry requires its actual base measurement")
        base = Fraction(capture.measured_base_quantity)
    if (
        base != Fraction(line.quantity)
        or (base * 10**item.quantity_decimal_places).denominator != 1
        or (base / Fraction(item.quantity_increment)).denominator != 1
        or (item.serial_tracking and base.denominator != 1)
    ):
        raise ValidationFailedError(
            "entered and base stock quantities do not agree with the native grid"
        )
