"""Bulk voucher import contracts; money is returned as exact decimal text."""

import datetime as dt
import uuid
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from vouchers.schemas.configuration import Contract

ImportFormat = Literal["CSV", "TSV", "XLSX", "JSON"]
JobState = Literal[
    "STAGED",
    "VALIDATING",
    "READY",
    "COMMITTING",
    "SUCCEEDED",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
]
RowState = Literal[
    "STAGED", "VALID", "WARNING", "INVALID", "BLOCKED", "CREATED", "FAILED", "NOT_SELECTED"
]
Digest = Field(pattern=r"^[0-9a-f]{64}$")
DuplicateRule = Literal["DATE_NUMBER_PARTY", "DATE_NUMBER", "DATE_NUMBER_ACCOUNT"]


class TemplateQuery(Contract):
    voucher_type_id: uuid.UUID
    format: ImportFormat = "XLSX"
    document_date: dt.date | None = None
    posting_date: dt.date | None = None
    class_id: uuid.UUID | None = None


class ImportStage(Contract):
    voucher_type_id: uuid.UUID
    format: ImportFormat
    # CSV/XLSX bytes (at most 8 MiB decoded); JSON uploads send ``document`` instead.
    content_base64: str | None = Field(default=None, min_length=4, max_length=11_200_000)
    document: dict[str, Any] | None = None
    template_id: uuid.UUID | None = None
    # A bill duplicates an existing voucher with the same bill number and bill date, plus the
    # same supplier party (default) or supplier ledger; DATE_NUMBER ignores the supplier.
    duplicate_rule: DuplicateRule = "DATE_NUMBER_PARTY"

    @model_validator(mode="after")
    def one_source(self) -> Self:
        if (self.format == "JSON") != (self.document is not None) or (self.format != "JSON") != (
            self.content_base64 is not None
        ):
            raise ValueError("JSON sends document; CSV and XLSX send content_base64")
        return self


class ImportVersion(Contract):
    expected_version: int = Field(strict=True, ge=1)


class ImportCommit(ImportVersion):
    selection_digest: str = Digest
    on_error: Literal["STOP", "CONTINUE_INDEPENDENT"] = "STOP"
    exclude_keys: tuple[str, ...] = Field(default=(), max_length=500)


class ImportQuery(Contract):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)
    state: JobState | None = None
    mine: bool = True


class ImportRowQuery(Contract):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)
    state: RowState | None = None


class ReportQuery(Contract):
    format: Literal["CSV", "TSV", "XLSX"] = "CSV"


class ReportDownload(ReportQuery):
    token: str = Field(min_length=1, max_length=4096)


class ImportJobListItem(Contract):
    id: uuid.UUID
    row_version: int
    kind: str
    source_format: ImportFormat
    state: JobState
    voucher_count: int
    valid_count: int
    warning_count: int
    invalid_count: int
    created_count: int
    failed_count: int
    own: bool
    created_at: dt.datetime


class ImportJobPage(Contract):
    items: list[ImportJobListItem]
    next_cursor: str | None


class ImportJobDetail(ImportJobListItem):
    revision: int
    company_id: uuid.UUID
    type_id: uuid.UUID
    type_revision_id: uuid.UUID
    on_error: Literal["STOP", "CONTINUE_INDEPENDENT"]
    duplicate_rule: DuplicateRule
    input_sha256: str
    selection_digest: str | None
    expires_at: dt.datetime


class ImportIssue(Contract):
    sheet: str
    row: int
    column: str | None
    code: str
    message: str
    layer: str
    # Warnings (possible duplicates) do not block; errors do.
    severity: Literal["error", "warning"] = "error"


class ImportVoucherListItem(Contract):
    id: uuid.UUID
    import_key: str
    ordinal: int
    state: RowState
    error_count: int
    currency: str | None
    declared_total: str | None
    computed_payable: str | None
    supplier_difference: str | None
    voucher_id: uuid.UUID | None
    row_version: int


class ImportVoucherPage(Contract):
    items: list[ImportVoucherListItem]
    next_cursor: str | None


class ImportVoucherDetail(ImportVoucherListItem):
    errors: list[ImportIssue]
    source_rows: list[tuple[str, int]]
    computed_tax_total: str | None
    # The uploader's own cells; omitted for other readers.
    source_input: dict[str, Any] | None = None


class ReportTicket(Contract):
    download_path: str
    expires_in: int


class ImportRevisionInput(ImportStage):
    expected_version: int = Field(strict=True, ge=1)


class TemplateSnapshotInput(Contract):
    voucher_type_id: uuid.UUID
    document_date: dt.date
    posting_date: dt.date
    class_id: uuid.UUID | None = None


class TemplateSnapshotDetail(Contract):
    id: uuid.UUID
    fingerprint: str
    expires_at: dt.datetime
    snapshot: dict[str, Any]


class HistoryQuery(Contract):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)


class RevisionItem(Contract):
    id: uuid.UUID
    revision: int
    source_format: ImportFormat
    source_sha256: str
    created_at: dt.datetime
    expires_at: dt.datetime


class AttemptItem(Contract):
    id: uuid.UUID
    revision_id: uuid.UUID
    phase: Literal["VALIDATE", "COMMIT"]
    outcome: str
    created_at: dt.datetime
    finished_at: dt.datetime | None


class HistoryPage(Contract):
    items: list[RevisionItem | AttemptItem]
    next_cursor: str | None


class AttemptResultPage(Contract):
    items: list[ImportVoucherDetail]
    next_cursor: str | None


class ImportDownload(Contract):
    kind: Literal["SOURCE", "NORMALIZED", "CORRECTION", "RESULT"] = "RESULT"
    format: ImportFormat = "CSV"
    revision: int | None = Field(default=None, ge=1)
    attempt_id: uuid.UUID | None = None


class ImportDownloadRequest(ImportDownload):
    token: str = Field(min_length=1, max_length=4096)
