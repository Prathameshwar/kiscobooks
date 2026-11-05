import uuid
from typing import Any, Literal

from pydantic import Field

from accounting.schemas.masters import AccountPostingMappingCreate, ExpectedVersion, Input


class ImportItem(Input):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,49}$")
    resource: str = Field(max_length=80)
    action: Literal["create", "update", "activate", "deactivate"] = "create"
    object_id: str | None = Field(default=None, max_length=60)
    values: dict[str, Any]


class ImportRequest(Input):
    items: list[ImportItem] = Field(min_length=1, max_length=200)


class ImportApply(ImportRequest):
    preview_token: str = Field(min_length=1, max_length=4096)


class ImportIssue(Input):
    key: str
    code: str


class ImportPreview(Input):
    valid: bool
    issues: list[ImportIssue]
    preview_token: str | None


class ImportResult(Input):
    records: dict[str, uuid.UUID]


class MappingDraftCreate(Input):
    values: AccountPostingMappingCreate


class MappingDraftUpdate(ExpectedVersion):
    values: AccountPostingMappingCreate


class MappingDraftDetail(Input):
    id: uuid.UUID
    row_version: int
    values: dict[str, Any]
    published_mapping_id: uuid.UUID | None


class HistoryItem(Input):
    id: uuid.UUID
    action: str
    object_version: int
    changed_fields: list[str]
    created_by: uuid.UUID | None
    created_at: str
