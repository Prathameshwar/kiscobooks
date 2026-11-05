"""Sparse, read-only native invoice facts with owner field policies."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.listing import PageMeta
from pydantic import Field

from accounting.schemas.masters import DecimalInput, Detail, Input


class InvoiceRecordDetail(Detail):
    intent_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    source_invoice_id: uuid.UUID | None = None
    calculation_version: int | None = None
    calculation_hash: str | None = None
    configuration_hash: str | None = None
    company_configuration_hash: str | None = None
    kind: str | None = None
    currency: str | None = None
    document_date: dt.date | None = None
    posting_date: dt.date | None = None
    party_account_id: uuid.UUID | None = None
    bill_reference: str | None = None
    due_date: dt.date | None = None
    commercial_total: DecimalInput | None = None
    tax_total: DecimalInput | None = None
    charged_tax_total: DecimalInput | None = None
    rounding: DecimalInput | None = None
    payable: DecimalInput | None = None
    supplier_declared_total: DecimalInput | None = None
    supplier_difference: DecimalInput | None = None
    supplier_difference_reason: str | None = None


class InvoiceSupplyFactDetail(Detail):
    invoice_id: uuid.UUID | None = None
    line_key: uuid.UUID | None = None
    sequence: int | None = None
    account_id: uuid.UUID | None = None
    supply_kind: str | None = None
    description: str | None = None
    entered: DecimalInput | None = None
    commercial: DecimalInput | None = None
    taxable: DecimalInput | None = None
    price_rounding: DecimalInput | None = None
    payable: DecimalInput | None = None
    tax_profile: str | None = None
    date_contract_version: int | None = None
    tax_point_date: dt.date | None = None
    tax_point_basis: str | None = None
    service_completion_date: dt.date | None = None
    company_registration_id: uuid.UUID | None = None
    party_registration_id: uuid.UUID | None = None
    place_of_supply: str | None = None
    supply_context: str | None = None
    classification_code: str | None = None
    treatment: str | None = None
    reverse_charge: bool | None = None
    credit_state: str | None = None
    supplier_invoice_number: str | None = None
    supplier_invoice_date: dt.date | None = None
    source_evidence: dict[str, Any] | None = None


class InvoiceComponentFactDetail(Detail):
    invoice_id: uuid.UUID | None = None
    component_key: uuid.UUID | None = None
    sequence: int | None = None
    purpose: str | None = None
    scope: str | None = None
    effect: str | None = None
    input_kind: str | None = None
    basis_amount: DecimalInput | None = None
    basis_quantity: DecimalInput | None = None
    input_amount: DecimalInput | None = None
    amount: DecimalInput | None = None
    account_id: uuid.UUID | None = None
    commercial_treatment: str | None = None
    tax_treatment: str | None = None
    return_treatment: str | None = None
    source_evidence: str | None = None


class InvoiceAllocationFactDetail(Detail):
    invoice_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    supply_id: uuid.UUID | None = None
    purpose: str | None = None
    amount: DecimalInput | None = None


class InvoiceTaxComponentDetail(Detail):
    invoice_id: uuid.UUID | None = None
    supply_id: uuid.UUID | None = None
    component_key: str | None = None
    code: str | None = None
    basis: DecimalInput | None = None
    amount: DecimalInput | None = None
    percentage: DecimalInput | None = None
    supplier_charged: bool | None = None
    rounding_mode: str | None = None
    source_version: int | None = None


class InvoicePostingLineDetail(Detail):
    tax_component_id: uuid.UUID | None = None
    tax_purpose: str | None = None
    invoice_id: uuid.UUID | None = None
    journal_line_id: uuid.UUID | None = None
    line_key: uuid.UUID | None = None
    sequence: int | None = None
    source_version: int | None = None
    purpose: str | None = None
    tracking: str | None = None
    bill_reference: str | None = None
    due_date: dt.date | None = None


class InvoiceRecordListItem(Input):
    id: uuid.UUID
    kind: str | None = None
    document_date: dt.date | None = None
    posting_date: dt.date | None = None
    party_account_id: uuid.UUID | None = None
    bill_reference: str | None = None
    currency: str | None = None
    payable: DecimalInput | None = None


class InvoiceRecordPage(Input):
    items: list[InvoiceRecordListItem]
    page: PageMeta


class InvoiceFactListItem(Input):
    id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    line_key: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    supply_id: uuid.UUID | None = None
    journal_line_id: uuid.UUID | None = None
    sequence: int | None = None
    purpose: str | None = None
    scope: str | None = None
    code: str | None = None
    amount: DecimalInput | None = None
    commercial: DecimalInput | None = None
    taxable: DecimalInput | None = None
    payable: DecimalInput | None = None
    tax_point_date: dt.date | None = None
    credit_state: str | None = None


class InvoiceFactPage(Input):
    items: list[InvoiceFactListItem]
    page: PageMeta


class InvoiceHistoryQuery(Input):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)


class InvoiceRecordQuery(InvoiceHistoryQuery):
    party_account_id: uuid.UUID | None = None
    kind: Literal["SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"] | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
