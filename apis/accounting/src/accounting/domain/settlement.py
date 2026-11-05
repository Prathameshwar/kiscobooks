"""Allocation arithmetic preserves the last carrying-value residual."""

from decimal import Decimal, localcontext

from billing_platform.errors import ValidationFailedError
from billing_platform.money import quantize_storage

from accounting.domain.ledger import exact_positive


def carrying_amount(
    amount: Decimal,
    base_amount: Decimal,
    remaining: Decimal,
    base_remaining: Decimal,
    allocated: Decimal,
) -> Decimal:
    for value in (amount, base_amount, allocated):
        exact_positive(value)
    if (
        not Decimal(0) < allocated <= remaining <= amount
        or not Decimal(0) <= base_remaining <= base_amount
    ):
        raise ValidationFailedError("allocation exceeds the available outstanding amount")
    with localcontext() as context:
        context.prec = 48
        return (
            base_remaining
            if allocated == remaining
            else min(base_remaining, quantize_storage(base_amount * allocated / amount))
        )
