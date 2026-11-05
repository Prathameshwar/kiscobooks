"""Exact warehouse cost consumption; physical origins are a separate allocation.

The owner loads and locks ordered pools/layers. These pure functions never infer
stock availability, substitute missing cost with zero, or choose a warehouse.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.money import RoundingMode

ZERO = Decimal("0.0000")
QUANTUM = Decimal("0.0001")
MAXIMUM = Decimal("999999999999999.9999")


def exact(value: Decimal, *, positive: bool = False) -> Decimal:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or value > MAXIMUM
        or (positive and value == 0)
    ):
        raise ValidationFailedError("stock quantity/value must be a bounded exact decimal")
    with localcontext() as context:
        context.prec = 64
        if value != value.quantize(QUANTUM):
            raise ValidationFailedError("stock quantity/value supports at most four decimal places")
    return value


@dataclass(frozen=True)
class CostBucket:
    identity: uuid.UUID
    quantity: Decimal
    value: Decimal

    def __post_init__(self) -> None:
        exact(self.quantity)
        exact(self.value)
        if self.quantity == 0 and self.value != 0:
            raise ConflictError("an empty cost bucket cannot retain carrying value")


@dataclass(frozen=True)
class CostTake:
    identity: uuid.UUID
    quantity: Decimal
    value: Decimal


def take(
    bucket: CostBucket,
    quantity: Decimal,
    *,
    places: int = 4,
    rounding: RoundingMode = RoundingMode.HALF_UP,
) -> CostTake:
    """Consume proportionally, assigning the entire residual to the final quantity."""
    exact(quantity, positive=True)
    if type(places) is not int or not 0 <= places <= 4:
        raise ValueError("currency precision must be between zero and four")
    if quantity > bucket.quantity:
        raise ConflictError("stock quantity exceeds its unconsumed cost")
    with localcontext() as context:
        context.prec = 64
        value = (
            bucket.value
            if quantity == bucket.quantity
            else (bucket.value * quantity / bucket.quantity).quantize(
                Decimal(1).scaleb(-places), rounding=rounding.decimal_rounding
            )
        )
    exact(value)
    return CostTake(bucket.identity, quantity, value)


def fifo(
    layers: Sequence[CostBucket],
    quantity: Decimal,
    *,
    places: int = 4,
    rounding: RoundingMode = RoundingMode.HALF_UP,
) -> tuple[CostTake, ...]:
    """Consume already ordered warehouse layers; do not conflate FEFO with costing."""
    exact(quantity, positive=True)
    if len({layer.identity for layer in layers}) != len(layers):
        raise ConflictError("cost layer identities must be distinct")
    if sum((layer.quantity for layer in layers), ZERO) < quantity:
        raise ConflictError("insufficient warehouse cost quantity")
    remaining = quantity
    allocations = []
    for layer in layers:
        if not remaining:
            break
        if not layer.quantity:
            continue
        consumed = take(layer, min(layer.quantity, remaining), places=places, rounding=rounding)
        allocations.append(consumed)
        remaining -= consumed.quantity
    return tuple(allocations)


def moving_average(
    pool: CostBucket,
    quantity: Decimal,
    *,
    places: int = 4,
    rounding: RoundingMode = RoundingMode.HALF_UP,
) -> CostTake:
    return take(pool, quantity, places=places, rounding=rounding)


def linked_return(
    original: CostBucket,
    returned_quantity: Decimal,
    returned_value: Decimal,
    quantity: Decimal,
    *,
    places: int = 4,
    rounding: RoundingMode = RoundingMode.HALF_UP,
) -> CostTake:
    """Reuse an original issue's remaining carrying cost, including its last residual."""
    exact(returned_quantity)
    exact(returned_value)
    if returned_quantity > original.quantity or returned_value > original.value:
        raise ConflictError("return claims exceed the original source")
    residual = CostBucket(
        original.identity, original.quantity - returned_quantity, original.value - returned_value
    )
    return take(residual, quantity, places=places, rounding=rounding)
