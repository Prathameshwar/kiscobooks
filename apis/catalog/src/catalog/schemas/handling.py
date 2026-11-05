"""Exact temperature bounds and ordinary native handling instructions."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal

from billing_platform.exact import exact_decimal
from billing_platform.listing import ListQuery
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from catalog.domain.profiles import HandlingRules
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import ExpectedVersion

ExactTemperature = Annotated[Decimal, BeforeValidator(exact_decimal, json_schema_input_type=str)]


class HandlingProfileCreate(MasterInput):
    pass


class HandlingProfileUpdate(MasterUpdate):
    pass


class HandlingProfileListItem(MasterListItem):
    pass


class HandlingProfileDetail(HandlingProfileListItem, DetailFields):
    pass


class HandlingProfileQuery(MasterQuery):
    pass


class HandlingDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("instructions")
    @classmethod
    def readable_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip() or any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("handling instructions must contain readable text")
        return value.strip()


class HandlingRevisionInput(HandlingDescription):
    temperature_min: ExactTemperature | None = None
    temperature_max: ExactTemperature | None = None
    temperature_unit: Literal["CELSIUS"] | None = None
    fragile: bool = Field(default=False, strict=True)
    keep_dry: bool = Field(default=False, strict=True)
    keep_upright: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def coherent(self) -> "HandlingRevisionInput":
        HandlingRules(
            self.temperature_min,
            self.temperature_max,
            self.temperature_unit,
            self.fragile,
            self.keep_dry,
            self.keep_upright,
        )
        return self


class HandlingRevisionUpdate(ExpectedVersion, HandlingDescription):
    temperature_min: ExactTemperature | None = None
    temperature_max: ExactTemperature | None = None
    temperature_unit: Literal["CELSIUS"] | None = None
    fragile: bool | None = Field(default=None, strict=True)
    keep_dry: bool | None = Field(default=None, strict=True)
    keep_upright: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def no_null_flags(self) -> "HandlingRevisionUpdate":
        if any(
            getattr(self, key) is None
            for key in self.model_fields_set & {"fragile", "keep_dry", "keep_upright"}
        ):
            raise ValueError("handling flags cannot be null")
        return self


class HandlingRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    profile_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    published_at: dt.datetime | None = None
    fragile: bool | None = None
    keep_dry: bool | None = None
    keep_upright: bool | None = None


class HandlingRevisionDetail(HandlingRevisionListItem, DetailFields, HandlingDescription):
    temperature_min: Decimal | None = None
    temperature_max: Decimal | None = None
    temperature_unit: Literal["CELSIUS"] | None = None


class HandlingRevisionQuery(ListQuery):
    published: bool | None = None
    fragile: bool | None = None
    keep_dry: bool | None = None
    keep_upright: bool | None = None
