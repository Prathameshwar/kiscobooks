"""Opening import, party documents and allocation contracts."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from accounting.schemas.ledger import Amount, BusinessDate, JournalCreate, JournalLineCreate, Rate
from accounting.schemas.masters import DecimalInput, Detail, ExpectedVersion, Input
from accounting.schemas.query import MasterQuery
from accounting.schemas.voucher_tax import SourceTax, validate_source_tax


class OpeningBill(Input):
    line_sequence: int = Field(strict=True, ge=1, le=200)
    reference: str = Field(min_length=1, max_length=120)
    amount: Amount
    document_date: BusinessDate | None = None
    due_date: BusinessDate | None = None
    source_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
    document_kind: Literal["INVOICE", "BILL", "CREDIT_NOTE", "ADVANCE", "ON_ACCOUNT"] | None = None
    original_amount: Amount | None = None
    base_amount: Amount | None = None

    @model_validator(mode="after")
    def outstanding(self) -> "OpeningBill":
        if self.document_kind == "ON_ACCOUNT":
            if self.document_date is not None or self.due_date is not None:
                raise ValueError("on-account openings have unknown invoice and due dates")
        elif self.document_date is None or self.due_date is None:
            raise ValueError("dated opening documents require invoice and due dates")
        if self.original_amount is not None and self.amount > self.original_amount:
            raise ValueError("outstanding cannot exceed original document amount")
        if not self.reference.strip() or any(ord(char) < 32 for char in self.reference):
            raise ValueError("enter a printable document reference")
        return self

    @model_serializer(mode="wrap")
    def legacy_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        for key in ("source_key", "document_kind", "original_amount", "base_amount"):
            if result.get(key) is None:
                result.pop(key, None)
        return result


class OpeningCreate(Input):
    posting_date: BusinessDate
    description: str = Field(min_length=3, max_length=1000)
    lines: list[JournalLineCreate] = Field(default_factory=list, max_length=200)
    bills: list[OpeningBill] = Field(default_factory=list, max_length=1000)
    replacement_of_id: uuid.UUID | None = None


class ZeroOpeningConfirm(Input):
    expected_setup_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ZeroOpeningReview(Input):
    company_id: uuid.UUID
    expected_setup_version: int
    books_begin_date: dt.date
    eligible: bool
    blocker: (
        Literal[
            "EXISTING_OPENING_OR_ACTIVITY", "BOOKS_PERIOD_NOT_OPEN", "OPENING_ALREADY_FINALIZED"
        ]
        | None
    )


class OpeningPreview(Input):
    posting_date: dt.date
    base_currency: str
    total_debit: DecimalInput
    total_credit: DecimalInput
    bill_count: int
    party_line_count: int
    zero_opening: bool


class SourceCreate(Input):
    kind: Literal["INVOICE", "BILL", "RECEIPT", "PAYMENT", "CREDIT_NOTE"]
    account_id: uuid.UUID
    counterpart_account_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount
    exchange_rate: Rate
    document_date: BusinessDate
    posting_date: BusinessDate
    due_date: BusinessDate | None = None
    reference: str = Field(min_length=1, max_length=120)
    source_system: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    source_type: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    source_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=3, max_length=1000)
    credit_reservation_id: uuid.UUID | None = None
    credit_override_id: uuid.UUID | None = None
    #: GST and TDS/TCS; ``amount`` is then the party amount the analysis must reproduce.
    tax: SourceTax | None = None

    @model_validator(mode="after")
    def tax_matches_kind(self) -> "SourceCreate":
        validate_source_tax(self.kind, self.tax)
        return self


class TaxPreviewRequest(Input):
    """Exactly one tax-bearing voucher request, exactly as it would be drafted."""

    journal: JournalCreate | None = None
    source_document: SourceCreate | None = None

    @model_validator(mode="after")
    def one_taxed_voucher(self) -> "TaxPreviewRequest":
        chosen = [item for item in (self.journal, self.source_document) if item is not None]
        if len(chosen) != 1 or chosen[0].tax is None:
            raise ValueError("preview exactly one journal or source document that carries tax")
        return self


class AllocationCreate(Input):
    debt_item_id: uuid.UUID
    credit_item_id: uuid.UUID
    posting_date: BusinessDate
    amount: Amount
    fx_account_id: uuid.UUID | None = None


class AllocationReverse(ExpectedVersion):
    posting_date: BusinessDate
    reason: str = Field(min_length=3, max_length=500)


class FinanceQuery(MasterQuery):
    period_id: uuid.UUID | None = None
    status: str | None = Field(default=None, max_length=20)
    journal_id: uuid.UUID | None = None
    journal_line_id: uuid.UUID | None = None
    direction: Literal["DEBT", "CREDIT"] | None = None
    debt_item_id: uuid.UUID | None = None
    credit_item_id: uuid.UUID | None = None
    posting_date: BusinessDate | None = None


class ItemQuery(Input):
    as_of: BusinessDate
    party_id: uuid.UUID
    role: Literal["CUSTOMER", "SUPPLIER"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    account_id: uuid.UUID | None = None


class Ageing(Input):
    as_of: dt.date
    party_id: uuid.UUID
    role: Literal["CUSTOMER", "SUPPLIER"]
    currency: str
    not_due: DecimalInput
    days_1_30: DecimalInput
    days_31_60: DecimalInput
    days_61_90: DecimalInput
    days_91_plus: DecimalInput
    unknown_due: DecimalInput
    debt: DecimalInput
    unapplied_credit: DecimalInput


class ItemBalance(Input):
    item_id: uuid.UUID
    as_of: dt.date
    currency: str
    remaining: DecimalInput
    base_currency: str
    base_remaining: DecimalInput


class OpeningBatchDetail(Detail):
    reversal_reason: str | None = None
    status: str | None = None
    posting_date: dt.date | None = None
    journal_id: uuid.UUID | None = None
    replacement_of_id: uuid.UUID | None = None
    description: str | None = None
    payload: dict[str, Any] | None = None
    finalized_at: dt.datetime | None = None


class OpeningBatchListItem(Detail):
    status: str | None = None
    posting_date: dt.date | None = None
    journal_id: uuid.UUID | None = None
    finalized_at: dt.datetime | None = None


class SourceDocumentDetail(Detail):
    journal_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: str | None = None
    status: str | None = None
    kind: str | None = None
    direction: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    posting_date: dt.date | None = None
    reference: str | None = None
    payload: dict[str, Any] | None = None


class SourceDocumentListItem(Detail):
    journal_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: str | None = None
    status: str | None = None
    kind: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    posting_date: dt.date | None = None
    reference: str | None = None


class OpenItemDetail(Detail):
    journal_line_id: uuid.UUID | None = None
    sequence: int | None = None
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: str | None = None
    direction: str | None = None
    reference: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    base_currency: str | None = None
    base_amount: DecimalInput | None = None
    document_date: dt.date | None = None
    posting_date: dt.date | None = None
    due_date: dt.date | None = None
    terms: dict[str, Any] | None = None
    reversal_journal_id: uuid.UUID | None = None
    reversal_date: dt.date | None = None


class OpenItemListItem(Detail):
    journal_line_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: str | None = None
    direction: str | None = None
    reference: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    posting_date: dt.date | None = None
    due_date: dt.date | None = None
    reversal_date: dt.date | None = None


class AllocationDetail(Detail):
    debt_item_id: uuid.UUID | None = None
    credit_item_id: uuid.UUID | None = None
    posting_date: dt.date | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    base_currency: str | None = None
    debt_base_amount: DecimalInput | None = None
    credit_base_amount: DecimalInput | None = None
    fx_journal_id: uuid.UUID | None = None
    reversal_date: dt.date | None = None
    reversal_reason: str | None = None
    fx_reversal_id: uuid.UUID | None = None


class AllocationListItem(Detail):
    debt_item_id: uuid.UUID | None = None
    credit_item_id: uuid.UUID | None = None
    posting_date: dt.date | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    reversal_date: dt.date | None = None
    fx_journal_id: uuid.UUID | None = None


class Reconciliation(Input):
    account_id: uuid.UUID
    as_of: dt.date
    currency: str
    ledger_balance: DecimalInput
    subledger_balance: DecimalInput
    difference: DecimalInput


class OpeningReopen(ExpectedVersion):
    reason: str = Field(min_length=3, max_length=500)
