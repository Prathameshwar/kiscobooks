"""Typed operation specifications; descriptive text cannot drive execution."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.configuration import ConfigurationOptionQuery
from catalog.schemas.units import ExpectedVersion


class OperationCreate(MasterInput):
    pass


class OperationUpdate(MasterUpdate):
    pass


class OperationListItem(MasterListItem):
    pass


class OperationDetail(OperationListItem, DetailFields):
    pass


class OperationQuery(MasterQuery):
    pass


class OperationServiceQuery(ConfigurationOptionQuery):
    kind: Literal["SERVICE"] = "SERVICE"


class OperationServiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    name: str
    sku: str | None = None
    status: Literal["ACTIVE"] = "ACTIVE"


def readable_text(value: str | None) -> str | None:
    if value is not None:
        if not value.strip() or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("enter readable operation text")
        return value.strip()
    return None


class OperationRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: str = Field(min_length=1, max_length=2000)
    change_reason: str = Field(min_length=1, max_length=500)
    service_item_id: uuid.UUID | None = None

    _text = field_validator("specification", "change_reason")(readable_text)


class OperationRevisionUpdate(ExpectedVersion):
    specification: str | None = Field(default=None, min_length=1, max_length=2000)
    change_reason: str | None = Field(default=None, min_length=1, max_length=500)
    service_item_id: uuid.UUID | None = None
    _text = field_validator("specification", "change_reason")(readable_text)

    @model_validator(mode="after")
    def required_text(self) -> "OperationRevisionUpdate":
        if any(
            getattr(self, key) is None
            for key in self.model_fields_set & {"specification", "change_reason"}
        ):
            raise ValueError("operation specification and reason cannot be cleared")
        return self


class OperationRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    operation_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"] | None = None
    published_at: dt.datetime | None = None
    service_item_id: uuid.UUID | None = None


class OperationRevisionDetail(OperationRevisionListItem, DetailFields):
    specification: str | None = None
    change_reason: str | None = None


class OperationRevisionQuery(ListQuery):
    published: bool | None = None
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"] | None = None
