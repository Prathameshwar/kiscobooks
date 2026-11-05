"""Explicit, previewed category scheme policy changes."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from catalog.schemas.classification import MembershipMode
from catalog.schemas.units import ExpectedVersion


class SchemeTransition(ExpectedVersion):
    membership_mode: MembershipMode
    is_required: StrictBool
    is_active: StrictBool


class SchemeTransitionCommit(SchemeTransition):
    preview_token: str = Field(min_length=1, max_length=8192)


class SchemeTransitionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheme_id: uuid.UUID
    expected_version: int
    category_count: int
    membership_count: int
    affected_family_count: int
    eligible: bool
    blockers: list[str]
    policy_generation: int
    source_version: int
    preview_token: str
