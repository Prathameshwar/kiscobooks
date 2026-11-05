"""Native profile inputs and protected projections; no physical device values."""

import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from catalog.domain.profiles import IdentifierRequirement, validate_identifier_requirements
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)


class IdentifierRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier_type: Literal["SERIAL", "IMEI"]
    namespace_rule: Literal["COMPANY", "MANUFACTURER_SKU"]
    min_count: int = Field(ge=0, le=8, strict=True)
    max_count: int = Field(ge=1, le=8, strict=True)
    requires_slot: StrictBool = False

    def rule(self) -> IdentifierRequirement:
        return IdentifierRequirement(
            self.identifier_type,
            self.namespace_rule,
            self.min_count,
            self.max_count,
            self.requires_slot,
        )

    @model_validator(mode="after")
    def supported(self) -> "IdentifierRequirementInput":
        self.rule()
        return self


class IdentifierProfileCreate(MasterInput):
    requirements: tuple[IdentifierRequirementInput, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def distinct(self) -> "IdentifierProfileCreate":
        validate_identifier_requirements(tuple(row.rule() for row in self.requirements))
        return self


class IdentifierProfileUpdate(MasterUpdate):
    pass


class IdentifierProfileListItem(MasterListItem):
    normalization_version: int | None = None


class IdentifierProfileDetail(IdentifierProfileListItem, DetailFields):
    pass


class IdentifierProfileQuery(MasterQuery):
    pass


class IdentifierRequirementListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    profile_id: uuid.UUID | None = None
    identifier_type: Literal["SERIAL", "IMEI"] | None = None
    namespace_rule: Literal["COMPANY", "MANUFACTURER_SKU"] | None = None
    min_count: int | None = None
    max_count: int | None = None
    requires_slot: bool | None = None


class IdentifierRequirementQuery(ListQuery):
    identifier_type: Literal["SERIAL", "IMEI"] | None = None
    namespace_rule: Literal["COMPANY", "MANUFACTURER_SKU"] | None = None
