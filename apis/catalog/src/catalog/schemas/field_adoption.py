"""Product field impact review is bounded and exposes no stored custom values."""

import uuid

from billing_platform.custom_fields import CustomDefinition
from pydantic import BaseModel, ConfigDict, Field


class AdoptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_token: str = Field(min_length=1, max_length=8192)


class AdoptionIssue(BaseModel):
    owner_id: uuid.UUID
    field_key: str
    reason: str


class AdoptionReview(BaseModel):
    entity_type: str
    owner_count: int
    eligible: bool
    issues: list[AdoptionIssue]
    definitions: list[CustomDefinition]
    source_definition_digests: dict[str, str]
    preview_token: str


class AdoptionResult(BaseModel):
    entity_type: str
    version: int
    owner_count: int
