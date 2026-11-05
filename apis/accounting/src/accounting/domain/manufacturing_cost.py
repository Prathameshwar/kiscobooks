"""Non-posting manufacturing output-cost allocation.

Actual cost, ownership, valuation policy and eligibility must be established by
Accounting's stock/WIP owner before this pure calculation can become an effect.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_calculation import apportion, exact


@dataclass(frozen=True, slots=True)
class CostPool:
    currency: str
    consumed_input: Decimal
    capitalizable_processing: Decimal
    capitalizable_overhead: Decimal
    nonrecoverable_input_tax: Decimal
    noncapitalizable_charge: Decimal


@dataclass(frozen=True, slots=True)
class OutputWeight:
    line_id: UUID
    item_id: UUID
    weight: Decimal


@dataclass(frozen=True, slots=True)
class OutputShare:
    line_id: UUID
    item_id: UUID
    allocated_cost: Decimal


@dataclass(frozen=True, slots=True)
class CostPreview:
    currency: str
    capitalizable_total: Decimal
    noncapitalizable_charge: Decimal
    outputs: tuple[OutputShare, ...]


def preview(pool: CostPool, outputs: tuple[OutputWeight, ...]) -> CostPreview:
    """Conserve four-place owner cost across explicit, distinct output lines."""
    if (
        len(pool.currency) != 3
        or not pool.currency.isalpha()
        or pool.currency != pool.currency.upper()
    ):
        raise ValidationFailedError("manufacturing cost requires an uppercase currency code")
    if not outputs or len(outputs) > 100:
        raise ValidationFailedError("manufacturing cost requires bounded outputs")
    if len({row.line_id for row in outputs}) != len(outputs):
        raise ValidationFailedError("manufacturing output lines must be distinct")
    if len({row.item_id for row in outputs}) != len(outputs):
        raise ValidationFailedError("manufacturing output SKUs must be distinct")
    parts = (
        pool.consumed_input,
        pool.capitalizable_processing,
        pool.capitalizable_overhead,
        pool.nonrecoverable_input_tax,
        pool.noncapitalizable_charge,
    )
    if any(exact(value) < 0 for value in parts):
        raise ValidationFailedError("manufacturing costs cannot be negative in a forward preview")
    capitalizable = sum(parts[:4], Decimal(0))
    exact(capitalizable)
    weights = tuple((str(row.line_id), exact(row.weight, scale=8)) for row in outputs)
    if any(weight < 0 for _, weight in weights):
        raise ValidationFailedError("manufacturing output weights cannot be negative")
    if sum((weight for _, weight in weights), Fraction()) <= 0:
        raise ValidationFailedError("manufacturing output allocation needs a positive basis")
    shares = apportion(capitalizable, weights, precision=4)
    return CostPreview(
        pool.currency,
        capitalizable,
        pool.noncapitalizable_charge,
        tuple(OutputShare(row.line_id, row.item_id, shares[str(row.line_id)]) for row in outputs),
    )
