"""Final manual-discount limits over the calculator's allocated consideration."""

from collections import defaultdict
from decimal import Decimal
from fractions import Fraction

from voucher_execution.invoice import InvoiceInput, InvoicePolicy

from accounting.domain.invoice_calculation import Calculation, refuse


def enforce_discount_limits(
    invoice: InvoiceInput, policy: InvoicePolicy, result: Calculation
) -> None:
    """Count every manual reduction once, before tax and without offsetting charges."""
    keys = {str(row.component_key) for row in invoice.components if row.purpose == "DISCOUNT"}
    if not keys:
        return
    discounts: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for row in result.allocations:
        if row.purpose == "COMMERCIAL" and row.component_key in keys:
            discounts[row.line_key] -= row.amount
    total = sum(discounts.values(), Decimal(0))
    if policy.max_discount_amount is not None and total > policy.max_discount_amount:
        refuse("manual discount exceeds configured invoice amount limit")
    entered = {row.key: row.entered for row in result.lines}
    for line_key, amount in discounts.items():
        if line_key not in entered or Fraction(amount) * 100 > (
            Fraction(entered[line_key]) * Fraction(policy.max_discount_pct)
        ):
            refuse("manual discount exceeds configured line percentage limit")
    if Fraction(total) * 100 > sum(
        (Fraction(value) for value in entered.values()), Fraction()
    ) * Fraction(policy.max_discount_pct):
        refuse("manual discount exceeds configured invoice percentage limit")
