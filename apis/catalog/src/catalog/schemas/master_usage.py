"""Bounded dependency metadata and protected usage pages."""

import uuid
from typing import Literal

from billing_platform.listing import ListQuery, Page
from pydantic import BaseModel, ConfigDict, Field


class UsageRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    entity_type: str
    field_key: str


class UsageCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relations: list[UsageRelation]
    coverage: Literal["permitted_local_relations"] = "permitted_local_relations"
    external_usage: Literal["unavailable"] = "unavailable"
    retirement_check: Literal["use_lifecycle_command"] = "use_lifecycle_command"


class UsageQuery(ListQuery):
    relation: str = Field(min_length=1, max_length=150)
    is_active: bool | None = None
    published: bool | None = None


class UsageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    entity_type: str
    field_key: str


class UsagePage(Page[UsageItem]):
    coverage: Literal["selected_local_relation"] = "selected_local_relation"
    external_usage: Literal["unavailable"] = "unavailable"
    retirement_check: Literal["use_lifecycle_command"] = "use_lifecycle_command"
