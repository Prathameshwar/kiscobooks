"""Exact entry validation and rational arithmetic, before any storage rounding.

Storage types retain their existing rounding contract. New quantity/rate entry paths
must validate here first: a value that loses information is an error, not a rounded
success. Product/unit eligibility and monetary rounding policy remain service-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import gcd

from billing_platform.constants import MONEY_MAX, MONEY_MIN
from billing_platform.money import MoneyError

type DecimalInput = Decimal | int | str

_STORAGE_QUANTUM = Decimal("0.0001")
_MAX_RATIO_PART = 2**63 - 1


def _decimal(value: DecimalInput) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
        raise MoneyError("use a Decimal, integer or decimal string")
    if isinstance(value, str) and len(value) > 128:
        raise MoneyError("decimal input exceeds the supported length")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError("invalid decimal input") from exc
    if not result.is_finite():
        raise MoneyError("decimal input must be finite")
    if not MONEY_MIN <= result <= MONEY_MAX:
        raise MoneyError("value exceeds DECIMAL(19,4)")
    return result


def _representable(value: DecimalInput, decimal_places: int) -> Decimal:
    result = _decimal(value)
    with localcontext(Context(prec=38)):
        rounded = result.quantize(Decimal(1).scaleb(-decimal_places))
        if rounded != result:
            raise MoneyError("value is not exactly representable at the accepted precision")
        return result.quantize(_STORAGE_QUANTUM)


def exact_decimal(
    value: DecimalInput,
    *,
    decimal_places: int = 4,
    increment: DecimalInput | None = None,
) -> Decimal:
    """Return an exact storage value, rejecting excess scale or off-grid entries.

    Insignificant trailing zeros are accepted. Signed values are supported because
    adjustments and reversals need them; positivity is a separate domain constraint.
    Integer-scaled checks avoid the caller's Decimal context affecting divisibility.
    """
    if type(decimal_places) is not int or not 0 <= decimal_places <= 4:
        raise MoneyError("decimal places must be an integer between 0 and 4")
    result = _representable(value, decimal_places)
    if increment is not None:
        step = _representable(increment, decimal_places)
        if step <= 0:
            raise MoneyError("increment must be positive")
        if (Fraction(result) / Fraction(step)).denominator != 1:
            raise MoneyError("value is not a multiple of the accepted increment")
    return result


def exact_rate(value: DecimalInput) -> Decimal:
    """Preserve an exact DECIMAL(19,8) rate without passing through money scale."""
    result = _decimal(value)
    scaled = Fraction(result) * 100_000_000
    if scaled.denominator != 1 or abs(scaled) >= 10**19:
        raise MoneyError("rate is not exactly representable as DECIMAL(19,8)")
    units = scaled.numerator
    return Decimal((int(units < 0), tuple(map(int, str(abs(units)))), -8))


@dataclass(frozen=True, slots=True)
class RationalConversion:
    """Positive canonical ratio; both components fit signed BIGINT storage."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        for value in (self.numerator, self.denominator):
            if type(value) is not int or not 1 <= value <= _MAX_RATIO_PART:
                raise MoneyError("conversion components must be positive signed BIGINT values")
        divisor = gcd(self.numerator, self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    def apply(self, value: DecimalInput) -> Fraction:
        """Preserve repeating results exactly; this is not a storage value."""
        return Fraction(exact_decimal(value)) * Fraction(self.numerator, self.denominator)

    def inverse(self) -> RationalConversion:
        return RationalConversion(self.denominator, self.numerator)


def convert_quantity(
    value: DecimalInput,
    conversion: RationalConversion,
    *,
    decimal_places: int = 4,
    increment: DecimalInput | None = None,
) -> Decimal:
    """Convert only when the target quantity is exactly representable."""
    scaled = conversion.apply(value) * 10_000
    if scaled.denominator != 1:
        raise MoneyError("converted quantity is not exactly representable in storage")
    # Construction from digits is exact even when a caller reduced Decimal precision.
    integer = scaled.numerator
    result = Decimal((int(integer < 0), tuple(map(int, str(abs(integer)))), -4))
    return exact_decimal(result, decimal_places=decimal_places, increment=increment)


def per_unit_ratio(amount: DecimalInput, basis_quantity: DecimalInput) -> Fraction:
    """Keep a per-N rate exact; do not round it into a different per-unit price."""
    basis = exact_decimal(basis_quantity)
    if basis <= 0:
        raise MoneyError("rate basis quantity must be positive")
    return Fraction(exact_decimal(amount)) / Fraction(basis)
