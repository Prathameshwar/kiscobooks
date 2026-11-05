"""Versioned import contracts shared by owner APIs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field

from billing_platform.bulk import BulkBatch, BulkRecord, ExactModel

FileFormat = Literal["CSV", "TSV", "XLSX"]
MARKER = "_import_schema_version"
MAX_COMMANDS = 200
CONTROLS = (
    "_key",
    "_set",
    "_resource",
    "_action",
    "_id",
    "_code",
    "_target_record",
    "_target_field",
    "_depends_on",
    "_clear_fields",
)


class TemplateRequest(ExactModel):
    definition: str = Field(pattern=r"^[a-z_]{1,40}$")
    parameters: dict[str, str] = Field(default_factory=dict, max_length=8)


class TemplateDetail(ExactModel):
    id: uuid.UUID
    definition: str
    fingerprint: str
    snapshot: dict[str, Any]
    expires_at: dt.datetime


class SourceFile(ExactModel):
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
    format: FileFormat
    content_base64: str = Field(min_length=1, max_length=12 * 1024 * 1024)


class StageImport(ExactModel):
    template_id: uuid.UUID
    mode: Literal["CREATE_ONLY", "UPDATE_ONLY", "UPSERT"] = "CREATE_ONLY"
    atomicity: Literal["CHANGE_SET", "ATOMIC"] = "CHANGE_SET"
    on_error: Literal["STOP", "CONTINUE_INDEPENDENT"] = "CONTINUE_INDEPENDENT"
    files: list[SourceFile] = Field(min_length=1, max_length=16)


class ImportAction(ExactModel):
    expected_version: int = Field(strict=True, ge=1, lt=2**31)


class CommitImport(ImportAction):
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviseImport(ImportAction):
    # Corrected files retain the same successful logical keys/aggregate definitions.
    files: list[SourceFile] = Field(min_length=1, max_length=16)


class ImportDetail(ExactModel):
    id: uuid.UUID
    definition: str
    state: str
    revision: int
    row_version: int
    record_count: int
    completed_count: int
    review_digest: str | None
    expires_at: dt.datetime
    created_at: dt.datetime


class DownloadOptions(ExactModel):
    kind: Literal["SOURCE", "NORMALIZED", "RESULT", "CORRECTION"] = "RESULT"
    format: FileFormat = "CSV"
    revision: int | None = Field(default=None, ge=1)
    attempt_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None


class DownloadRequest(DownloadOptions):
    token: str = Field(min_length=1, max_length=4096)


class DownloadTicket(ExactModel):
    token: str
    expires_in: int = 300


class ImportBatch(BulkBatch):
    """The native graph is shared; this release deliberately narrows capacity."""

    records: list[BulkRecord] = Field(min_length=1, max_length=MAX_COMMANDS)


class ImportDefinition(ExactModel):
    key: str
    label: str


class ImportDefinitions(ExactModel):
    items: list[ImportDefinition]
    formats: list[FileFormat]
    maximum_commands: int


class ImportJobListItem(ExactModel):
    id: uuid.UUID
    definition: str
    state: str
    revision: int
    row_version: int
    record_count: int
    completed_count: int
    created_at: dt.datetime
    expires_at: dt.datetime


class ImportAttemptItem(ExactModel):
    id: uuid.UUID
    revision_id: uuid.UUID
    phase: str
    outcome: str
    created_at: dt.datetime
    finished_at: dt.datetime


class ImportRevisionItem(ExactModel):
    id: uuid.UUID
    revision: int
    input_hash: str
    created_at: dt.datetime


class ImportArtifactItem(ExactModel):
    id: uuid.UUID
    revision_id: uuid.UUID
    filename: str
    format: str
    byte_count: int
    content_sha256: str
    expires_at: dt.datetime


class ImportRecordItem(ExactModel):
    id: uuid.UUID
    logical_key: str
    resource: str
    source_file: str
    source_sheet: str
    source_row: int
    status: str | None
    business_id: uuid.UUID | None


class ImportIssueItem(ExactModel):
    id: uuid.UUID
    record_id: uuid.UUID
    field: str
    code: str
    message: str
