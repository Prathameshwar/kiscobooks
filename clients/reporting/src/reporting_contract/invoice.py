"""Immutable invoice, component and credit source grains; no executable tax rules."""

import datetime as dt
import uuid
from typing import Annotated

from billing_platform.exact import exact_decimal, exact_rate
from pydantic import BeforeValidator

from reporting_contract.base import Contract


def amount(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("report amounts require decimal strings")
    return format(exact_decimal(value), "f")


def rate(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("report rates require decimal strings")
    return format(exact_rate(value), "f")


Amount = Annotated[str, BeforeValidator(amount)]
Rate = Annotated[str, BeforeValidator(rate)]


class InvoiceRecord(Contract):
    intent_id: uuid.UUID
    revision_id: uuid.UUID
    source_invoice_id: uuid.UUID | None = None
    calculation_version: int
    calculation_hash: str
    configuration_hash: str
    company_configuration_hash: str
    kind: str
    currency: str
    document_date: dt.date
    posting_date: dt.date
    party_account_id: uuid.UUID
    bill_reference: str
    due_date: dt.date
    commercial_total: Amount
    tax_total: Amount
    charged_tax_total: Amount
    rounding: Amount
    payable: Amount
    supplier_declared_total: Amount | None
    supplier_difference: Amount | None
    supplier_difference_reason: str | None


class InvoiceSupplyFact(Contract):
    invoice_id: uuid.UUID
    line_key: uuid.UUID
    # Accepted common item line; absent on older snapshots, never inferred from text.
    item_line_key: uuid.UUID | None = None
    sequence: int
    account_id: uuid.UUID
    supply_kind: str
    description: str
    entered: Amount
    commercial: Amount
    taxable: Amount
    price_rounding: Amount
    payable: Amount
    tax_profile: str
    date_contract_version: int
    tax_point_date: dt.date | None
    tax_point_basis: str | None
    service_completion_date: dt.date | None
    company_registration_id: uuid.UUID | None
    party_registration_id: uuid.UUID | None
    place_of_supply: str | None
    supply_context: str | None
    classification_code: str | None
    treatment: str
    reverse_charge: bool
    credit_state: str
    supplier_invoice_number: str | None
    supplier_invoice_date: dt.date | None


class InvoiceComponentFact(Contract):
    invoice_id: uuid.UUID
    component_key: uuid.UUID
    sequence: int
    purpose: str
    scope: str
    effect: str
    input_kind: str
    basis_amount: Amount
    basis_quantity: Amount | None
    input_amount: Amount
    amount: Amount
    account_id: uuid.UUID | None
    commercial_treatment: str
    tax_treatment: str
    return_treatment: str
    source_evidence: str


class InvoiceAllocationFact(Contract):
    invoice_id: uuid.UUID
    component_id: uuid.UUID
    supply_id: uuid.UUID
    purpose: str
    amount: Amount


class InvoiceTaxComponent(Contract):
    invoice_id: uuid.UUID
    supply_id: uuid.UUID
    component_key: str
    code: str
    basis: Amount
    amount: Amount
    percentage: Rate
    supplier_charged: bool
    rounding_mode: str
    source_version: int


class InvoicePostingLine(Contract):
    invoice_id: uuid.UUID
    journal_line_id: uuid.UUID
    tax_component_id: uuid.UUID | None
    tax_purpose: str | None
    line_key: uuid.UUID
    sequence: int
    source_version: int
    purpose: str
    tracking: str
    bill_reference: str | None
    due_date: dt.date | None


class InvoiceCreditAction(Contract):
    invoice_id: uuid.UUID
    component_id: uuid.UUID
    expected_event_id: uuid.UUID
    kind: str
    amount: Amount
    event_date: dt.date
    posting_date: dt.date
    currency: str
    journal_id: uuid.UUID | None
    offset_account_id: uuid.UUID | None
    cash_deposit_line_id: uuid.UUID | None
    annual_return_filed_on: dt.date | None
    document_verified: bool
    supply_received: bool
    business_use: bool
    restrictions_checked: bool
    supplier_report_matched: bool
    tax_payment_verified: bool
    return_filed: bool
    supplier_paid: bool
    reference: str
    evidence_sha256: str
    reason: str


class InvoiceCreditEvent(Contract):
    invoice_id: uuid.UUID
    action_id: uuid.UUID


INVOICE_FACT_MODELS: dict[str, type[Contract]] = {
    "invoice_record": InvoiceRecord,
    "invoice_supply_fact": InvoiceSupplyFact,
    "invoice_component_fact": InvoiceComponentFact,
    "invoice_allocation_fact": InvoiceAllocationFact,
    "invoice_tax_component": InvoiceTaxComponent,
    "invoice_posting_line": InvoicePostingLine,
    "invoice_credit_action": InvoiceCreditAction,
    "invoice_credit_event": InvoiceCreditEvent,
}
