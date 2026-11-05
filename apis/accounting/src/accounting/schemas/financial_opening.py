"""Versioned financial migration declarations; master creation has no money effects."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.listing import ListQuery
from pydantic import Field, model_validator

from accounting.schemas.ledger import Amount, BusinessDate, Rate
from accounting.schemas.masters import ExpectedVersion, Input
from accounting.schemas.subledger import OpeningBill


class OpeningDocument(OpeningBill):
    line_sequence: int = Field(default=1, ge=1, le=200, strict=True)
    document_date: BusinessDate
    due_date: BusinessDate
    document_kind: Literal["INVOICE", "BILL", "CREDIT_NOTE", "ADVANCE"] | None = None


class OnAccountOpeningDocument(OpeningBill):
    line_sequence: int = Field(default=1, ge=1, le=200, strict=True)
    document_kind: Literal["ON_ACCOUNT"]
    document_date: None = None
    due_date: None = None


class OpeningEntry(Input):
    source_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount
    exchange_rate: Rate
    base_amount: Amount | None = None
    description: str | None = Field(default=None, max_length=500)
    documents: list[OpeningDocument | OnAccountOpeningDocument] = Field(
        default_factory=list, max_length=1000
    )


class OpeningYtdAmount(Input):
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount
    base_amount: Amount


class OpeningDeclaration(Input):
    version: Literal[1] = 1
    posting_date: BusinessDate
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_system: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,59}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
    covered_through: BusinessDate
    originating_year_start: BusinessDate | None = None
    coverage_mode: Literal["POST_CUTOVER_ONLY", "YTD_SUMMARY"] = "POST_CUTOVER_ONLY"
    ytd_summary: list[OpeningYtdAmount] | None = Field(default=None, max_length=10000)
    same_day_reviewed: bool = Field(default=False, strict=True)
    credit_cash_reviewed: bool = Field(default=False, strict=True)
    credit_cash_reason: str | None = Field(default=None, min_length=3, max_length=500)
    clearing_account_id: uuid.UUID | None = None
    replacement_of_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=500)
    entries: list[OpeningEntry] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def coherent(self) -> "OpeningDeclaration":
        if self.covered_through > self.posting_date or (
            self.covered_through == self.posting_date and not self.same_day_reviewed
        ):
            raise ValueError("coverage must precede cutover unless same-day review is explicit")
        if self.originating_year_start and self.originating_year_start > self.posting_date:
            raise ValueError("originating year cannot follow the cutover")
        if self.coverage_mode == "YTD_SUMMARY":
            if self.originating_year_start is None or self.ytd_summary is None:
                raise ValueError(
                    "YTD coverage requires a fiscal-year start and explicit nominal summary"
                )
            if (
                not self.originating_year_start <= self.covered_through < self.posting_date
                or (self.posting_date - self.covered_through).days != 1
            ):
                raise ValueError(
                    "YTD coverage must run from fiscal-year start through the day before cutover"
                )
        elif self.ytd_summary is not None:
            raise ValueError("post-cutover-only declarations cannot claim imported YTD activity")
        if len({entry.source_key.casefold() for entry in self.entries}) != len(self.entries):
            raise ValueError("opening entry source keys must be unique")
        if sum(len(entry.documents) for entry in self.entries) > 10000:
            raise ValueError("opening declaration exceeds ten thousand documents")
        if not self.reason.strip() or any(ord(char) < 32 for char in self.reason):
            raise ValueError("enter a printable audit reason")
        for entry in self.entries:
            for document in entry.documents:
                if (
                    document.document_date is not None
                    and document.document_date > self.covered_through
                ):
                    raise ValueError("opening document falls outside declared source coverage")
                if entry.currency != self.currency and document.base_amount is None:
                    raise ValueError(
                        "foreign opening bills require their historical base carrying values"
                    )
        if self.credit_cash_reviewed and (
            not self.credit_cash_reason or len(self.credit_cash_reason.strip()) < 3
        ):
            raise ValueError("reviewing credit cash requires an explanation")
        return self


class OpeningRevisionCommand(ExpectedVersion):
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def printable_reason(self) -> "OpeningRevisionCommand":
        if len(self.reason.strip()) < 3 or any(ord(char) < 32 for char in self.reason):
            raise ValueError("enter a printable review reason of at least three characters")
        return self


class OpeningReplace(OpeningRevisionCommand):
    declaration: OpeningDeclaration


class OpeningWorkspaceDetail(Input):
    id: uuid.UUID
    company_id: uuid.UUID
    status: str
    posting_date: dt.date
    expected_version: int
    revision_id: uuid.UUID
    manifest_hash: str
    currency: str
    coverage_mode: str
    entry_count: int
    document_count: int
    expected_debit: str
    expected_credit: str
    journal_ids: list[uuid.UUID]
    posted_journals: int
    blockers: list[str]
    effect_kind: Literal["PREPARATION", "PARTIALLY_POSTED", "POSTED"]


class OpeningEntryQuery(ListQuery):
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    side: Literal["DEBIT", "CREDIT"] | None = None
    source_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")


class OpeningEntryItem(Input):
    id: uuid.UUID
    source_key: str
    account_id: uuid.UUID
    party_id: uuid.UUID | None
    role: str | None
    side: str
    currency: str
    amount: str
    base_amount: str
    document_count: int


class OpeningEntryPostingLink(Input):
    entry_id: uuid.UUID
    source_key: str
    chunk_id: uuid.UUID
    journal_id: uuid.UUID | None
    line_sequence: int
    journal_status: str


class FinancialOpeningRevisionItem(Input):
    id: uuid.UUID
    revision: int
    manifest_hash: str
    created_at: dt.datetime


class FinancialOpeningReadiness(Input):
    company_id: uuid.UUID
    books_begin_date: dt.date
    currency: str
    batch_id: uuid.UUID | None
    status: str
    blockers: list[str]
    can_prepare: bool


class FinancialOpeningCapabilities(Input):
    company_id: uuid.UUID
    schema_version: Literal[1] = 1
    opening_date: Literal["BOOKS_BEGIN_DATE"] = "BOOKS_BEGIN_DATE"
    maximum_entries: int = 10000
    maximum_documents: int = 10000
    maximum_native_lines: int = 200
    maximum_native_documents: int = 1000
    draft_chunks_per_request: int = 2
    unknown_history_supported: Literal[True] = True
    ytd_summary_supported: Literal[True] = True
    clearing_chunks_supported: Literal[True] = True
    credit_cash_requires_review: Literal[True] = True
    master_creation_posts_money: Literal[False] = False
    execution_effect: Literal["NATIVE_JOURNAL_DRAFTS"] = "NATIVE_JOURNAL_DRAFTS"
    finalization: Literal["EXPLICIT_AFTER_NATIVE_CONFIRMATION"] = (
        "EXPLICIT_AFTER_NATIVE_CONFIRMATION"
    )


class FinancialOpeningPreview(Input):
    company_id: uuid.UUID
    manifest_hash: str
    posting_date: dt.date
    currency: str
    total_debit: str
    total_credit: str
    entry_count: int
    document_count: int
    journal_count: int
    coverage_mode: str
    covered_through: dt.date
    informational_only: Literal[True] = True


class FinancialOpeningExportTicket(Input):
    token: str
    download_path: str
    expires_in: int = 300


class OpeningReconciliation(Input):
    batch_id: uuid.UUID
    revision_id: uuid.UUID
    posting_date: dt.date
    covered_through: dt.date
    coverage_mode: str
    currency: str
    expected_debit: str
    expected_credit: str
    posted_debit: str
    posted_credit: str
    declared_documents: int
    posted_documents: int
    gl_matches: bool
    party_items_match: bool
    confirmation_pending: bool
    ready_to_finalize: bool
    blockers: list[str]
    clearing_balance: str
    clearing_account_id: uuid.UUID | None
    bank_gl_debit: str
    bank_gl_credit: str
    bank_opening_items_path: str
    stock_opening_control_path: str
    bank_reconciliation: Literal["SEPARATE_OWNER"] = "SEPARATE_OWNER"
    physical_inventory: Literal["SEPARATE_OWNER"] = "SEPARATE_OWNER"
    pre_cutover_transactions_available: Literal[False] = False
    annual_carry: Literal["DERIVED_FROM_POSTED_FACTS"] = "DERIVED_FROM_POSTED_FACTS"


class OpeningJournalRecovery(Input):
    company_id: uuid.UUID
    batch_id: uuid.UUID
    journal_id: uuid.UUID
    journal_status: str
    expected_version: int
    can_cancel: bool
    can_reverse: bool
    reversal_blockers: list[str]
    reversal_journal_id: uuid.UUID | None
    reversal_status: str | None
    reversal_expected_version: int | None
    can_cancel_reversal: bool


class FinancialOpeningCaptureMetadata(Input):
    schema_version: Literal[1] = 1
    capture: dict[str, Any]
    permission_sources: list[str]
    native_field_sets: list[str]
    posting_date_source: Literal["company.books_begin_date"]
    capture_permissions: dict[str, dict[str, bool]]
