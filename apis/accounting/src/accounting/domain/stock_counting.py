"""Count valuation follows verified native cost; ambiguity is a review state."""

from collections.abc import Sequence
from decimal import Decimal, localcontext
from fractions import Fraction

from billing_platform.errors import ConflictError
from billing_platform.money import RoundingMode

from accounting.domain.stock_costing import CostBucket, exact


def verified_cost(
    method: str, pool: CostBucket | None, layers: Sequence[CostBucket]
) -> Fraction | None:
    if pool is None or pool.quantity == 0:
        return None
    if method == "MOVING_AVERAGE":
        return Fraction(pool.value) / Fraction(pool.quantity)
    if method != "FIFO":
        raise ConflictError("count valuation requires FIFO or moving average")
    remaining = [layer for layer in layers if layer.quantity]
    if (
        sum((layer.quantity for layer in remaining), Decimal(0)) != pool.quantity
        or sum((layer.value for layer in remaining), Decimal(0)) != pool.value
    ):
        raise ConflictError("FIFO count costs do not reconcile to their native pool")
    costs = {Fraction(layer.value) / Fraction(layer.quantity) for layer in remaining}
    return next(iter(costs)) if len(costs) == 1 else None


def surplus_value(
    quantity: Decimal, cost: Fraction, places: int, rounding: RoundingMode
) -> Decimal:
    value = Fraction(quantity) * cost
    with localcontext() as context:
        context.prec = 64
        rounded = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
            Decimal(1).scaleb(-places), rounding=rounding.decimal_rounding
        )
    return exact(rounded)
