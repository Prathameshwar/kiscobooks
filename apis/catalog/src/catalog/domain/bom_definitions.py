"""Pure physical-grid and batch constraints for non-posting BOM definitions."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import ceil
from uuid import UUID

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import RationalConversion, exact_decimal
from billing_platform.money import MoneyError

from catalog.domain.units import QuantityRule, storage_quantity


@dataclass(frozen=True, slots=True)
class BatchRule:
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    multiple: Decimal | None = None

    def __post_init__(self) -> None:
        try:
            for value in (self.minimum, self.maximum, self.multiple):
                if value is not None and exact_decimal(value) <= 0:
                    raise ValidationFailedError("batch constraints must be positive")
        except MoneyError as exc:
            raise ValidationFailedError("batch constraints must be exact quantities") from exc
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValidationFailedError("minimum batch exceeds maximum batch")
        if self.maximum is not None and self.multiple is not None:
            first = max(1, ceil(Fraction(self.minimum or self.multiple) / Fraction(self.multiple)))
            if first * Fraction(self.multiple) > Fraction(self.maximum):
                raise ValidationFailedError("batch range contains no permitted positive multiple")

    def validate(
        self, nominal: Decimal, run_count: int | None, runs: tuple[Decimal, ...] | None
    ) -> None:
        try:
            expected = exact_decimal(nominal)
        except MoneyError as exc:
            raise ValidationFailedError("nominal batch output must be an exact quantity") from exc
        if expected <= 0:
            raise ValidationFailedError("nominal batch output must be positive")
        if run_count is not None and (type(run_count) is not int or not 1 <= run_count <= 1000):
            raise ValidationFailedError("run count must be a positive bounded integer")
        constrained = any(
            value is not None for value in (self.minimum, self.maximum, self.multiple)
        )
        if runs is None:
            if constrained:
                raise ValidationFailedError("batch constraints require an explicit run breakdown")
            return
        if type(run_count) is not int or not 1 <= run_count <= 1000 or len(runs) != run_count:
            raise ValidationFailedError("run breakdown must match the explicit run count")
        try:
            values = tuple(exact_decimal(value) for value in runs)
        except MoneyError as exc:
            raise ValidationFailedError("run sizes must be exact quantities") from exc
        if sum((Fraction(value) for value in values), Fraction()) != Fraction(expected):
            raise ValidationFailedError("run sizes must equal the nominal output quantity")
        for value in values:
            if value <= 0 or (self.minimum is not None and value < self.minimum):
                raise ValidationFailedError("run size is below the permitted minimum")
            if self.maximum is not None and value > self.maximum:
                raise ValidationFailedError("run size exceeds the permitted maximum")
            if (
                self.multiple is not None
                and (Fraction(value) / Fraction(self.multiple)).denominator != 1
            ):
                raise ValidationFailedError("run size is outside the permitted batch increment")


@dataclass(frozen=True, slots=True)
class PhysicalQuantity:
    item_id: UUID
    entered: QuantityRule
    base: QuantityRule
    conversion: RationalConversion
    serialized: bool = False
    fractional_entry: bool = True

    def validate(self, quantity: Decimal) -> Decimal:
        try:
            value = self.entered.validate(quantity)
            if value < 0:
                raise ValidationFailedError("physical quantity cannot be negative")
            if not self.fractional_entry and value != value.to_integral_value():
                raise ValidationFailedError("fractional unit entry is disabled")
            result = self.base.validate(storage_quantity(self.conversion.apply(value)))
            if self.serialized and result != result.to_integral_value():
                raise ValidationFailedError("serialized base quantities must be whole")
            return result
        except MoneyError as exc:
            raise ValidationFailedError(
                "quantity does not fit its pinned physical unit grid"
            ) from exc
