"""Manual limits apply to allocated reductions rather than netted invoice totals."""

from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from voucher_execution.invoice import InvoiceComponent, InvoiceInput, InvoicePolicy

from accounting.domain.invoice_calculation import Allocation, Calculation, SupplyResult
from accounting.domain.invoice_discounts import enforce_discount_limits


def test_discount_limit_checks_each_line_and_does_not_net_charges():
    key = uuid7()
    invoice = InvoiceInput.model_construct(
        components=(InvoiceComponent.model_construct(component_key=key, purpose="DISCOUNT"),)
    )
    lines = (
        SupplyResult("a", Decimal(100), Decimal(90), Decimal(90), (), Decimal(0), Decimal(90)),
        SupplyResult("b", Decimal(100), Decimal(70), Decimal(70), (), Decimal(0), Decimal(70)),
    )
    allocations = (
        Allocation(str(key), "a", "COMMERCIAL", Decimal(-10)),
        Allocation(str(key), "b", "COMMERCIAL", Decimal(-30)),
        Allocation("charge", "b", "COMMERCIAL", Decimal(100)),
    )
    result = Calculation(
        1, lines, (), allocations, Decimal(160), Decimal(0), Decimal(0), Decimal(0), Decimal(160)
    )
    policy = InvoicePolicy(manual_discounts_allowed=True, max_discount_pct=Decimal(20))
    with pytest.raises(ValidationFailedError, match="line percentage"):
        enforce_discount_limits(invoice, policy, result)
    with pytest.raises(ValidationFailedError, match="amount limit"):
        enforce_discount_limits(
            invoice, policy.model_copy(update={"max_discount_amount": Decimal(39)}), result
        )
    enforce_discount_limits(
        invoice, policy.model_copy(update={"max_discount_pct": Decimal(30)}), result
    )
