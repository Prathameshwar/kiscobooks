"""Versioned staged inputs and lean, protected job/record contracts."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from billing_platform.bulk import MAX_ROWS, BulkBatch, BulkRecord, ExactModel
from billing_platform.listing import ListQuery
from pydantic import Field, field_serializer, field_validator


class JsonStage(BulkBatch):
    format: Literal["JSON"] = "JSON"


class FileStage(ExactModel):
    format: Literal["CSV", "XLSX"]
    schema_version: Literal[1] = 1
    mode: Literal["CREATE_ONLY", "UPDATE_ONLY", "UPSERT"] = "CREATE_ONLY"
    atomicity: Literal["CHANGE_SET", "ATOMIC"] = "CHANGE_SET"
    on_error: Literal["STOP", "CONTINUE_INDEPENDENT"] = "STOP"
    content_base64: str = Field(min_length=1, max_length=12 * 1024 * 1024)


class FilterStage(ExactModel):
    format: Literal["FILTER"]
    schema_version: Literal[1] = 1
    resource: Literal["product_family", "item", "unit_of_measure", "item_price"]
    action: Literal["UPDATE", "ADJUST"] = "UPDATE"
    filters: dict[str, str | bool] = Field(default_factory=dict, max_length=8)
    all_rows: bool = Field(default=False, strict=True)
    data: dict[str, Any]
    clear_fields: list[str] = Field(default_factory=list, max_length=100)
    atomicity: Literal["CHANGE_SET", "ATOMIC"] = "CHANGE_SET"
    on_error: Literal["STOP", "CONTINUE_INDEPENDENT"] = "STOP"

    @field_validator("data")
    @classmethod
    def exact_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return BulkRecord.exact_data(value)


StageInput = Annotated[JsonStage | FileStage | FilterStage, Field(discriminator="format")]


class JobAction(ExactModel):
    expected_version: int = Field(strict=True, ge=1, lt=2**31)


class ValidateJob(JobAction):
    selected_keys: list[str] | None = Field(default=None, min_length=1, max_length=MAX_ROWS)


class CommitJob(JobAction):
    selection_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReviseJob(JobAction):
    batch: BulkBatch


class JobListItem(ExactModel):
    id: uuid.UUID
    company_id: uuid.UUID
    kind: str
    state: str
    row_version: int
    revision: int
    record_count: int
    completed_count: int
    invalid_count: int
    created_at: dt.datetime


class JobDetail(JobListItem):
    actor_user_id: uuid.UUID
    mode: str
    atomicity: str
    on_error: str
    schema_version: int
    selection_digest: str | None
    policy_generation: int | None
    source_version: int | None
    expires_at: dt.datetime


class RecordListItem(ExactModel):
    id: uuid.UUID
    logical_key: str
    change_set_id: uuid.UUID
    resource: str
    action: str
    source_sheet: str
    source_row: int
    state: str
    error_code: str | None


def ratio_wire_values(resource: str, values: dict[str, Any] | None) -> dict[str, Any] | None:
    """Render exact ratios without altering persisted evidence or permission inputs."""
    if values is None or resource not in {"unit_conversion", "item_unit_revision"}:
        return values
    return {
        key: str(value) if key in {"numerator", "denominator"} and value is not None else value
        for key, value in values.items()
    }


class ResourceChange(ExactModel):
    resource: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    @field_serializer("before", "after", when_used="json")
    def exact_values(self, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return ratio_wire_values(self.resource, value)


class RecordPreview(RecordListItem):
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    changes: list[ResourceChange] = Field(default_factory=list)
    error_fields: list[str] = Field(default_factory=list)

    @field_serializer("before", "after", "result", when_used="json")
    def exact_values(self, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return ratio_wire_values(self.resource, value)


class BulkQuery(ListQuery):
    q: None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)
    state: str | None = Field(default=None, pattern=r"^[A-Z_]{1,20}$")
    sort: Literal["id", "-id"] = "id"


class Template(ExactModel):
    resource: str
    actions: list[str]
    schema_version: int = 1
    schema_document: dict[str, Any]
    required_permissions: list[str]


class TemplateQuery(ExactModel):
    resource: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    action: str = Field(default="CREATE", pattern=r"^[A-Z][A-Z_]{0,39}$")
    format: Literal["JSON", "CSV", "XLSX"] = "JSON"


class ReportOptions(ExactModel):
    format: Literal["CSV", "XLSX"] = "CSV"


class ReportDownload(ReportOptions):
    token: str = Field(min_length=1, max_length=4096)


class ReportTicket(ExactModel):
    download_path: str
    expires_in_seconds: Literal[300] = 300
