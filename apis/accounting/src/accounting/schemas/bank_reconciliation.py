"""Reviewed CSV statements, bank matches and statement-period reconciliation."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from accounting.schemas.masters import DecimalInput, Detail, Input


class MappingCreate(Input):
    account_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    date_column: str = Field(min_length=1, max_length=120)
    debit_column: str = Field(min_length=1, max_length=120)
    credit_column: str = Field(min_length=1, max_length=120)
    reference_column: str = Field(min_length=1, max_length=120)
    description_column: str = Field(min_length=1, max_length=120)
    transaction_id_column: str | None = Field(default=None, max_length=120)
    currency_column: str | None = Field(default=None, max_length=120)
    account_column: str | None = Field(default=None, max_length=120)
    account_value: str | None = Field(default=None, max_length=120)
    balance_column: str | None = Field(default=None, max_length=120)
    date_format: str = Field(default="%Y-%m-%d", max_length=40)
    delimiter: Literal[",", ";", "\t"] = ","


class MappingView(Detail):
    account_id: uuid.UUID | None = None
    revision: int | None = None
    currency: str | None = None
    columns: dict[str, str | None] | None = None


class StatementUpload(Input):
    mapping_id: uuid.UUID
    content_base64: str = Field(min_length=1, max_length=3_000_000)
    period_from: dt.date
    period_to: dt.date
    opening_balance: DecimalInput
    closing_balance: DecimalInput


class ImportView(Detail):
    account_id: uuid.UUID | None = None
    mapping_id: uuid.UUID | None = None
    file_sha256: str | None = None
    currency: str | None = None
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    opening_balance: DecimalInput | None = None
    closing_balance: DecimalInput | None = None
    row_count: int | None = None
    status: str | None = None
    review_reason: str | None = None


class ImportDecision(Input):
    reason: str = Field(min_length=3, max_length=500)


class DuplicateDecision(ImportDecision):
    disposition: Literal["ACCEPTED", "EXISTING"]


class EntryView(Detail):
    import_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    line_number: int | None = None
    transaction_date: dt.date | None = None
    side: str | None = None
    amount: DecimalInput | None = None
    currency: str | None = None
    reference: str | None = None
    description: str | None = None
    transaction_id: str | None = None
    row_sha256: str | None = None
    review_status: str | None = None
    running_balance: DecimalInput | None = None


class MatchLine(Input):
    statement_entry_id: uuid.UUID
    instrument_id: uuid.UUID
    amount: DecimalInput = Field(gt=0)


class MatchCommand(Input):
    group_id: uuid.UUID
    parts: list[MatchLine] = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=3, max_length=500)


class UnmatchCommand(ImportDecision):
    pass


class MatchView(Detail):
    statement_entry_id: uuid.UUID | None = None
    instrument_id: uuid.UUID | None = None
    amount: DecimalInput | None = None
    bank_date: dt.date | None = None
    group_id: uuid.UUID | None = None
    reverses_id: uuid.UUID | None = None
    reason: str | None = None


class MatchAssessment(Input):
    statement_residuals: dict[uuid.UUID, DecimalInput]
    instrument_residuals: dict[uuid.UUID, DecimalInput]


class SessionCreate(Input):
    account_id: uuid.UUID
    period_from: dt.date
    period_to: dt.date
    opening_balance: DecimalInput
    closing_balance: DecimalInput
    reason: str = Field(min_length=3, max_length=500)


class SessionView(Detail):
    account_id: uuid.UUID | None = None
    currency: str | None = None
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    generation: int | None = None
    opening_balance: DecimalInput | None = None
    closing_balance: DecimalInput | None = None
    status: str | None = None
    snapshot: dict[str, object] | None = None
    reason: str | None = None


class OpeningCreate(Input):
    instrument_id: uuid.UUID
    cutoff_date: dt.date
    amount: DecimalInput = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class OpeningView(Detail):
    account_id: uuid.UUID | None = None
    instrument_id: uuid.UUID | None = None
    cutoff_date: dt.date | None = None
    amount: DecimalInput | None = None
    currency: str | None = None
    reason: str | None = None


class CandidateView(Input):
    statement_entry_id: uuid.UUID
    instrument_id: uuid.UUID
    remaining_statement: DecimalInput
    remaining_book: DecimalInput
    rank: int
    reason: Literal["REFERENCE_AND_AMOUNT", "AMOUNT_AND_DATE", "POTENTIAL"]


class PolicyCreate(Input):
    account_id: uuid.UUID
    mode: Literal["MANUAL_ONLY", "SUGGEST_AND_REVIEW"]
    match_window_days: int = Field(default=30, ge=0, le=90)
    require_separate_reviewer: bool = False


class PolicyView(Detail):
    account_id: uuid.UUID | None = None
    revision: int | None = None
    mode: str | None = None
    match_window_days: int | None = None
    require_separate_reviewer: bool | None = None


class ProposalCreate(Input):
    statement_entry_id: uuid.UUID
    kind: Literal["PAYMENT", "RECEIPT", "CONTRA", "JOURNAL"]
    reason: str = Field(min_length=3, max_length=500)


class ProposalDecision(Input):
    reason: str = Field(min_length=3, max_length=500)
    voucher_id: uuid.UUID | None = None


class ProposalView(Detail):
    statement_entry_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    kind: str | None = None
    amount: DecimalInput | None = None
    currency: str | None = None
    status: str | None = None
    voucher_id: uuid.UUID | None = None
    reason: str | None = None
    decision_reason: str | None = None
