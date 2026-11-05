"""Bounded, native stack policy authoring and protected publication history."""

import datetime as dt
import uuid
from typing import Literal, Self

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalog.schemas.promotions import StackGroup, StackPermission, StackPolicyTerms
from catalog.schemas.units import ExpectedVersion, UnitCreate


class StackDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    change_reason: str = Field(min_length=1, max_length=500)
    maximum_applied: int = Field(strict=True, ge=1, le=10)
    groups: tuple[StackGroup, ...] = Field(default=(), max_length=20)
    permissions: tuple[StackPermission, ...] = Field(default=(), max_length=190)

    @model_validator(mode="after")
    def reviewed(self) -> Self:
        self.change_reason = UnitCreate.meaningful_label(self.change_reason)
        if self.groups:
            StackPolicyTerms(
                groups=self.groups,
                permissions=self.permissions,
                maximum_applied=self.maximum_applied,
            )
        elif self.permissions:
            raise ValueError("stack permissions require their reviewed groups")
        return self


class StackDraftUpdate(StackDraftInput, ExpectedVersion):
    pass


class StackQuery(ListQuery):
    code: str | None = Field(
        default=None, min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$"
    )
    status: Literal["DRAFT", "PUBLISHED"] | None = None


class StackDraftListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    maximum_applied: int | None = None
    row_version: int | None = None
    status: Literal["DRAFT", "PUBLISHED"] | None = None
    group_count: int | None = None
    permission_count: int | None = None
    published_policy_id: uuid.UUID | None = None


class StackDraftDetail(StackDraftListItem):
    company_id: uuid.UUID
    policy_generation: int
    change_reason: str | None = None
    complete: bool
    groups: tuple[StackGroup, ...] | None = None
    permissions: tuple[StackPermission, ...] | None = None
    operational_ready: Literal[False] = False


class StackPolicyListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    version: int | None = None
    maximum_applied: int | None = None
    published_at: dt.datetime | None = None


class StackPolicyDetail(StackPolicyListItem):
    company_id: uuid.UUID
    source_sha256: str | None = None
    complete: bool
    groups: tuple[StackGroup, ...] | None = None
    permissions: tuple[StackPermission, ...] | None = None
    operational_ready: Literal[False] = False


class StackAuthoringContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    enabled: bool
    operational_ready: Literal[False] = False
