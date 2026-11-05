"""Private job definitions stay internal; status reveals only authorized evidence."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field


class RebuildStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(strict=True, ge=0, lt=2**63)


class RebuildCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(strict=True, ge=1, lt=2**63)


class RebuildQuery(ListQuery):
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"] | None = None


class IndexStateDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    entity_type: str
    field_key: str
    row_version: int
    generation: int
    ready_generation: int | None
    building_generation: int | None
    retired_generation: int | None
    ready_for_current_definition: bool


class RebuildListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    generation: int
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    phase: Literal["build", "cleanup", "complete"]
    processed_count: int
    row_version: int
    created_at: dt.datetime


class RebuildDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    company_id: uuid.UUID
    entity_type: str
    field_key: str
    actor_user_id: uuid.UUID
    generation: int
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    phase: Literal["build", "cleanup", "complete"]
    processed_count: int
    cleanup_count: int
    reason_code: str | None
    row_version: int
    created_at: dt.datetime
    updated_at: dt.datetime
