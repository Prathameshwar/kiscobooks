"""Native warranty definitions; coverage text never drives claim calculations."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from catalog.domain.profiles import WarrantyRules
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import ExpectedVersion

DurationUnit = Literal["DAYS", "MONTHS", "YEARS"]
StartTrigger = Literal["SALE", "DELIVERY", "INSTALLATION"]


def coverage_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip() or any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError("coverage description must contain readable text")
    return value.strip()


class WarrantyPolicyCreate(MasterInput):
    pass


class WarrantyPolicyUpdate(MasterUpdate):
    pass


class WarrantyPolicyListItem(MasterListItem):
    pass


class WarrantyPolicyDetail(WarrantyPolicyListItem, DetailFields):
    pass


class WarrantyPolicyQuery(MasterQuery):
    pass


class WarrantyRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: int = Field(ge=1, le=36500, strict=True)
    duration_unit: DurationUnit
    start_trigger: StartTrigger = "SALE"
    coverage_description: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("coverage_description")
    @classmethod
    def readable_coverage(cls, value: str | None) -> str | None:
        return coverage_text(value)

    @model_validator(mode="after")
    def coherent(self) -> "WarrantyRevisionInput":
        WarrantyRules(self.duration, self.duration_unit, self.start_trigger)
        return self


class WarrantyRevisionUpdate(ExpectedVersion):
    duration: int | None = Field(default=None, ge=1, le=36500, strict=True)
    duration_unit: DurationUnit | None = None
    start_trigger: StartTrigger | None = None
    coverage_description: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("coverage_description")
    @classmethod
    def readable_coverage(cls, value: str | None) -> str | None:
        return coverage_text(value)

    @model_validator(mode="after")
    def no_null_requirements(self) -> "WarrantyRevisionUpdate":
        if any(
            getattr(self, key) is None for key in self.model_fields_set - {"coverage_description"}
        ):
            raise ValueError("warranty duration and trigger cannot be cleared")
        return self


class WarrantyRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    policy_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    published_at: dt.datetime | None = None
    duration: int | None = None
    duration_unit: DurationUnit | None = None
    start_trigger: StartTrigger | None = None


class WarrantyRevisionDetail(WarrantyRevisionListItem, DetailFields):
    coverage_description: str | None = None


class WarrantyRevisionQuery(ListQuery):
    published: bool | None = None
    duration_unit: DurationUnit | None = None
    start_trigger: StartTrigger | None = None
