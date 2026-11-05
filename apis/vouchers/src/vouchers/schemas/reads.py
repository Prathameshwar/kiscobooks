"""Lean list projections and explicit response envelopes."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.listing import PageMeta
from pydantic import Field, model_validator
from voucher_execution.invoice import InvoiceInput, Value
from voucher_execution.money import MoneyInput
from voucher_execution.stock import StockInput

from vouchers.schemas.configuration import Contract
from vouchers.schemas.documents import AssignmentInput, CounterInput, FulfillmentTermsInput


class ResourceItem(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    type_id: uuid.UUID | None = None
    type_code: str | None = None
    document_date: dt.date | None = None
    issue_number: str | None = None
    status: str | None = None
    code: str | None = None
    name: str | None = None
    kind: str | None = None
    profile: str | None = None
    current_revision: int | None = None
    revision_number: int | None = None
    outlet_id: uuid.UUID | None = None
    # The counterparty ledger account for this invoice; a display name is never replicated
    # here, only resolved by the caller from Accounting's own account read.
    party_account_id: uuid.UUID | None = None
    ref_number: str | None = None
    amount: Value | None = None
    # Always alongside `amount`: a currency-less amount risks borrowing the viewer's or
    # company's default currency symbol for a row denominated in another currency
    # (CLAUDE.md §6.1 money correctness).
    currency: str | None = None


class ResourcePage(Contract):
    items: list[ResourceItem]
    page: PageMeta


class ResourceDetail(ResourceItem):
    derived_from_revision_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    policy: dict[str, Any] | None = None
    fields: list[str] | None = None
    title: str | None = None
    prefix: str | None = None
    padding: int | None = None
    type_revision_id: uuid.UUID | None = None
    family: str | None = None


class OperationDetail(Contract):
    id: uuid.UUID
    voucher_id: uuid.UUID
    revision_id: uuid.UUID
    status: str
    purpose: str
    attempt_count: int
    row_version: int
    rejection_code: str | None = None


class AssignmentDetail(AssignmentInput):
    source_code: str | None = None
    source_name: str | None = None


class VoucherDetail(Contract):
    stock: StockInput | None = None
    financial: MoneyInput | None = None
    invoice: InvoiceInput | None = None
    fulfillment_terms: FulfillmentTermsInput | None = None
    assignments: list[AssignmentDetail] | None = None
    counter: CounterInput | None = None
    cashier_id: uuid.UUID | None = None
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    status: str
    kind: str | None = None
    profile: str | None = None
    revision_id: uuid.UUID
    revision_number: int
    content_hash: str | None = None
    configuration_hash: str | None = None
    fiscal_start_date: dt.date | None = None
    issue_number: str | None = None
    type_revision_id: uuid.UUID
    class_id: uuid.UUID | None = None
    document_date: dt.date | None = None
    posting_date: dt.date | None = None
    stock_date: dt.date | None = None
    statutory_date: dt.date | None = None
    credit_terms_date: dt.date | None = None
    mode: str | None = None
    currency: str | None = None
    narration: str | None = None
    lines: list[dict[str, Any]] | None = None
    parties: list[dict[str, Any]] | None = None
    references: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None
    links: list[dict[str, Any]] | None = None
    custom_fields: dict[str, Any] | None = None


class ListQuery(Contract):
    q: str | None = Field(default=None, max_length=100)
    sort: Literal["id", "-id", "document_date", "-document_date"] = "id"
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)
    status: str | None = Field(default=None, max_length=20)
    code: str | None = Field(default=None, max_length=40)
    type_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    kind: str | None = Field(default=None, max_length=40)
    document_from: dt.date | None = None
    document_to: dt.date | None = None
    issue_number: str | None = Field(default=None, max_length=100)
    custom_entity: Literal["vouchers.voucher", "vouchers.voucher_item"] = "vouchers.voucher"
    type_revision_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    outlet_id: uuid.UUID | None = None
    assignment_role: (
        Literal["SELLER", "BROKER", "COLLECTOR", "RETURN_HANDLER", "PAYMENT_HANDLER"] | None
    ) = None
    assignment_principal_id: uuid.UUID | None = None
    counter_id: uuid.UUID | None = None
    custom_key: str | None = Field(default=None, pattern=r"^cf_[a-z][a-z0-9_]{0,59}$")
    custom_value: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid_document_range(self) -> "ListQuery":
        if (
            self.document_from is not None
            and self.document_to is not None
            and self.document_from > self.document_to
        ):
            raise ValueError("document_from must be on or before document_to")
        return self
