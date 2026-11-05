"""Posting preconditions a calculation can already prove, so acceptance cannot outrun posting."""

import datetime as dt
from typing import Any

from voucher_execution.invoice import InvoiceCalculationDetail, InvoiceInput


def posting_problem(
    kind: str,
    document_date: dt.date,
    invoice: InvoiceInput,
    calculation: InvoiceCalculationDetail,
) -> str | None:
    """Mirror the posting refusals in ``invoice_execution.resolve`` that need no ledger state."""
    if calculation.payable <= 0:
        return "invoice must have positive consideration"
    if invoice.due_date < document_date:
        return "invoice due date cannot precede the document date"
    if calculation.rounding and invoice.rounding_account_id is None:
        return "calculated price/invoice rounding requires its posting account"
    evidence: dict[str, Any] = {str(row["line_key"]): row for row in calculation.tax_evidence}
    for line in calculation.lines:
        for tax in line.taxes:
            purposes = ["OUTPUT_" + tax.code] if kind == "SALES" else []
            if kind == "PURCHASE":
                if evidence[str(line.key)]["credit_state"] == "PENDING_EVIDENCE":
                    purposes.append("PENDING_" + tax.code)
                if not tax.supplier_charged:
                    purposes.append("RCM_" + tax.code)
            mappings = evidence[str(line.key)]["posting_mappings"]
            for purpose in purposes:
                mapping = next((row for row in mappings if row["purpose"] == purpose), None)
                if mapping is None or not mapping["ready"]:
                    return "tax posting mapping is missing or ambiguous"
    return None
