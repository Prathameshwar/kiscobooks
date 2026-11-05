"""What a purchased goods line adds to stock (B24, owner decision 2026-11-03).

The line's commercial value already carries its discounts and the supplier charges
apportioned to it by value; GST that cannot be claimed as input credit is capitalised on
top. Claimable GST is recoverable tax, never stock, and price/invoice rounding is never
capitalised. Pure arithmetic over exact decimals: no framework, no database.
"""

from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol


class ChargedTax(Protocol):
    @property
    def amount(self) -> Decimal: ...

    @property
    def supplier_charged(self) -> bool: ...


def landed_cost(commercial: Decimal, taxes: Iterable[ChargedTax], *, claimable: bool) -> Decimal:
    if not isinstance(commercial, Decimal) or commercial < 0:
        raise ValueError("a goods line's commercial value is a non-negative exact decimal")
    capitalised = (
        Decimal(0)
        if claimable
        else sum((tax.amount for tax in taxes if tax.supplier_charged), Decimal(0))
    )
    return commercial + capitalised
