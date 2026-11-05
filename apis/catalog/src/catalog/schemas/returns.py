"""Native return windows and a bounded set of supported eligibility conditions."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalog.domain.profiles import ReturnRules
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import ExpectedVersion

ConditionCode = Literal[
    "ORIGINAL_PACKAGING",
    "PROOF_OF_PURCHASE",
    "COMPLETE_ACCESSORIES",
    "UNUSED",
    "UNDAMAGED",
]


class ReturnPolicyCreate(MasterInput):
    pass


class ReturnPolicyUpdate(MasterUpdate):
    pass


class ReturnPolicyListItem(MasterListItem):
    pass


class ReturnPolicyDetail(ReturnPolicyListItem, DetailFields):
    pass


class ReturnPolicyQuery(MasterQuery):
    pass


class ReturnRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    returns_allowed: bool = Field(default=False, strict=True)
    window_days: int | None = Field(default=None, ge=0, le=36500, strict=True)
    condition_codes: tuple[ConditionCode, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def coherent(self) -> "ReturnRevisionInput":
        ReturnRules(self.returns_allowed, self.window_days, self.condition_codes)
        return self


class ReturnRevisionUpdate(ExpectedVersion):
    returns_allowed: bool | None = Field(default=None, strict=True)
    window_days: int | None = Field(default=None, ge=0, le=36500, strict=True)
    condition_codes: tuple[ConditionCode, ...] | None = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def no_null_requirements(self) -> "ReturnRevisionUpdate":
        if any(getattr(self, key) is None for key in self.model_fields_set - {"window_days"}):
            raise ValueError("return flag and condition set cannot be null")
        return self


class ReturnRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    policy_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    published_at: dt.datetime | None = None
    returns_allowed: bool | None = None
    window_days: int | None = None
    condition_count: int | None = None


class ReturnRevisionDetail(ReturnRevisionListItem, DetailFields):
    pass


class ReturnRevisionQuery(ListQuery):
    published: bool | None = None
    returns_allowed: bool | None = None


class ReturnConditionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    revision_id: uuid.UUID | None = None
    condition_code: ConditionCode | None = None


class ReturnConditionQuery(ListQuery):
    condition_code: ConditionCode | None = None
