"""Exact SKU/master grids and transaction role admission, without owner I/O."""

from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ConflictError, ValidationFailedError

from vouchers.schemas.sources import ItemUnitFacts, UnitMasterFacts


def grid(quantity: Fraction, places: int, increment: Decimal) -> None:
    if (quantity * 10**places).denominator != 1 or (
        quantity / Fraction(increment)
    ).denominator != 1:
        raise ValidationFailedError("quantity does not follow the product unit precision/increment")
    if quantity < 0 or quantity > Fraction("999999999999999.9999"):
        raise ValidationFailedError("converted quantity exceeds DECIMAL(19,4)")


def admit_quantity(
    quantity: Decimal,
    selected: ItemUnitFacts,
    master: UnitMasterFacts,
    base: ItemUnitFacts,
    base_master: UnitMasterFacts,
) -> Fraction | None:
    value = Fraction(quantity)
    grid(value, master.decimal_places, master.quantity_increment)
    grid(value, selected.quantity_decimal_places, selected.quantity_increment)
    if not selected.fractional_entry and value.denominator != 1:
        raise ValidationFailedError("quantity requires whole product units")
    if selected.conversion_mode == "FIXED":
        if master.dimension != base_master.dimension:
            raise ConflictError("fixed product unit dimension differs from its base unit")
        assert selected.numerator is not None and selected.denominator is not None
        converted = value * Fraction(int(selected.numerator), int(selected.denominator))
        grid(converted, base_master.decimal_places, base_master.quantity_increment)
        grid(converted, base.quantity_decimal_places, base.quantity_increment)
        if not base.fractional_entry and converted.denominator != 1:
            raise ValidationFailedError("converted quantity requires whole base product units")
        return converted
    return None


def admit_role(selected: ItemUnitFacts, kind: str | None) -> None:
    if kind in {"SALES", "SALES_ORDER", "DELIVERY_NOTE", "REJECTIONS_IN", "CREDIT_NOTE"}:
        if selected.usage_role == "PURCHASE":
            raise ConflictError("product unit is not enabled for sales")
    if kind in {"PURCHASE", "PURCHASE_ORDER", "RECEIPT_NOTE", "REJECTIONS_OUT", "DEBIT_NOTE"}:
        if selected.usage_role == "SALE":
            raise ConflictError("product unit is not enabled for purchases")
