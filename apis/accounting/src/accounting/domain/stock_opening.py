"""Exact opening arithmetic; callers supply authenticated published unit rules."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from billing_platform.errors import ValidationFailedError
from billing_platform.money import RoundingMode

from accounting.domain.stock_costing import exact


@dataclass(frozen=True)
class OpeningCalculation:
    base_quantity: Decimal
    value: Decimal
    derived_unit_cost: Decimal
    derived_base_unit_cost: Decimal


def calculate(
    *,
    entered_quantity: Decimal,
    numerator: int | None,
    denominator: int | None,
    entered_increment: Decimal,
    base_increment: Decimal,
    entered_places: int,
    base_places: int,
    serialized: bool,
    cost_mode: str,
    unit_cost: Decimal | None,
    priced_quantity: Decimal,
    received_value: Decimal | None,
    places: int,
    rounding: RoundingMode,
    conversion_mode: str = "FIXED",
    measured_base_quantity: Decimal | None = None,
) -> OpeningCalculation:
    exact(entered_quantity, positive=True)
    exact(entered_increment, positive=True)
    exact(base_increment, positive=True)
    exact(priced_quantity, positive=True)
    if conversion_mode not in {"FIXED", "MEASURED"}:
        raise ValidationFailedError("opening conversion mode is unsupported")
    if any(
        type(value) is not int or not 0 <= value <= 4
        for value in (entered_places, base_places, places)
    ):
        raise ValidationFailedError("opening precision must be between zero and four")
    if conversion_mode == "FIXED" and any(
        type(value) is not int or not 0 < value <= 9_223_372_036_854_775_807
        for value in (numerator, denominator)
    ):
        raise ValidationFailedError("opening conversion requires a published positive ratio")
    if conversion_mode == "FIXED" and measured_base_quantity is not None:
        raise ValidationFailedError("fixed opening cannot accept a measured override")
    if conversion_mode == "MEASURED" and (
        numerator is not None or denominator is not None or measured_base_quantity is None
    ):
        raise ValidationFailedError("measured opening requires its actual base measurement")
    with localcontext() as context:
        context.prec = 80
        if entered_quantity % entered_increment or entered_quantity != entered_quantity.quantize(
            Decimal(1).scaleb(-entered_places)
        ):
            raise ValidationFailedError("opening entered quantity does not fit its published grid")
        # Test divisibility before division: repeating rationals must never be
        # rounded into a representable physical quantity.
        if conversion_mode == "FIXED":
            assert numerator is not None and denominator is not None
            scaled = entered_quantity * numerator * Decimal(10_000)
            if scaled % denominator:
                raise ValidationFailedError("opening conversion is not exactly representable")
            base = entered_quantity * numerator / denominator
        else:
            assert measured_base_quantity is not None
            base = measured_base_quantity
        exact(base, positive=True)
        if (
            base % base_increment
            or base != base.quantize(Decimal(1).scaleb(-base_places))
            or (serialized and base != base.to_integral_value())
        ):
            raise ValidationFailedError("opening base quantity does not fit its published grid")
        quantum = Decimal(1).scaleb(-places)
        if cost_mode == "RATE" and unit_cost is not None:
            exact(unit_cost)
            amount = (entered_quantity * unit_cost / priced_quantity).quantize(
                quantum, rounding=rounding.decimal_rounding
            )
            if received_value is not None and received_value != amount:
                raise ValidationFailedError(
                    "opening rate and value do not agree at company precision"
                )
        elif cost_mode == "VALUE" and unit_cost is None and received_value is not None:
            amount = received_value
        else:
            raise ValidationFailedError("opening valuation needs its explicit RATE or VALUE input")
        exact(amount)
        if amount != amount.quantize(quantum):
            raise ValidationFailedError("opening value exceeds company monetary precision")
        return OpeningCalculation(
            base,
            amount,
            (amount * priced_quantity / entered_quantity).quantize(
                Decimal("0.0001"), rounding=rounding.decimal_rounding
            ),
            (amount / base).quantize(Decimal("0.0001"), rounding=rounding.decimal_rounding),
        )
