"""Decimal helpers. Money is ``Decimal`` end to end — never ``float``.

Two separate scales, and conflating them is the bug this module exists to prevent:

* **Storage scale** is fixed at 4 for every amount and quantity, everywhere.
* **Display / rounding scale** is per company (``amount_precision``,
  ``quantity_precision``, 0-4) and is what computed totals round *to*.

Rounding happens once, at a documented boundary (line total, then document
total), never progressively through intermediate arithmetic.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Final

from billing_platform.constants import MONEY_MAX, MONEY_MIN, MONEY_SCALE

_STORAGE_EXPONENT: Final = Decimal(1).scaleb(-MONEY_SCALE)  # Decimal("0.0001")


class RoundingMode(StrEnum):
    """``company.rounding_mode`` values, mapped to Python rounding constants."""

    HALF_UP = "half_up"
    HALF_EVEN = "half_even"
    DOWN = "down"

    @property
    def decimal_rounding(self) -> str:
        return _ROUNDING_MAP[self]


_ROUNDING_MAP: Final[dict[RoundingMode, str]] = {
    RoundingMode.HALF_UP: "ROUND_HALF_UP",
    RoundingMode.HALF_EVEN: "ROUND_HALF_EVEN",
    RoundingMode.DOWN: "ROUND_DOWN",
}


class MoneyError(ValueError):
    """Raised when a value cannot be represented as platform money."""


def to_decimal(value: Decimal | int | str) -> Decimal:
    """Coerce to ``Decimal``, rejecting ``float`` outright.

    ``float`` is rejected rather than converted because the loss has already
    happened by the time the value arrives — ``0.1 + 0.2`` is not ``0.3`` before
    this function ever sees it.
    """
    if isinstance(value, float):  # pragma: no cover - defensive, mypy blocks it
        raise MoneyError("float is never a money value; pass Decimal, int or str")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise MoneyError(f"not a decimal value: {value!r}") from exc


def quantize_storage(value: Decimal | int | str) -> Decimal:
    """Quantize to the fixed 4-place storage scale.

    Applied on the way into a ``DECIMAL(19,4)`` column so truncation is explicit
    and testable here, rather than silent in MariaDB.
    """
    dec = to_decimal(value)
    with localcontext() as ctx:
        ctx.prec = 38
        quantized = dec.quantize(_STORAGE_EXPONENT, rounding="ROUND_HALF_UP")
    if quantized > MONEY_MAX or quantized < MONEY_MIN:
        raise MoneyError(f"value out of DECIMAL(19,4) range: {dec}")
    return quantized


def round_for_display(
    value: Decimal | int | str,
    precision: int,
    mode: RoundingMode = RoundingMode.HALF_UP,
) -> Decimal:
    """Round to a company's display precision (0-4).

    This is the *only* place a computed total is rounded. It returns a
    ``Decimal`` at the requested scale, not a string — formatting is separate.
    """
    if not 0 <= precision <= MONEY_SCALE:
        raise MoneyError(f"precision must be 0..{MONEY_SCALE}, got {precision}")
    dec = to_decimal(value)
    with localcontext() as ctx:
        ctx.prec = 38
        return dec.quantize(Decimal(1).scaleb(-precision), rounding=mode.decimal_rounding)


def is_zero(value: Decimal) -> bool:
    """Scale-insensitive zero test. ``Decimal("0.0000") != Decimal("0")`` compares
    equal under ``==``, but ``bool()`` and string comparison do not."""
    return value.is_zero()
