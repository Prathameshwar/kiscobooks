"""Stable mastered identifier codes with protected, lean wire projections."""

import datetime as dt
import uuid

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from catalog.schemas.units import ExpectedVersion, UnitCreate


class IdentifierNamespaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def printable(self) -> "IdentifierNamespaceCreate":
        self.name = UnitCreate.meaningful_label(self.name)
        return self


class IdentifierTypeCreate(IdentifierNamespaceCreate):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=100)
    is_barcode: StrictBool


class IdentifierNamespaceUpdate(ExpectedVersion):
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def printable(self) -> "IdentifierNamespaceUpdate":
        if "name" in self.model_fields_set:
            if self.name is None:
                raise ValueError("name cannot be cleared")
            self.name = UnitCreate.meaningful_label(self.name)
        return self


class IdentifierTypeUpdate(IdentifierNamespaceUpdate):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class IdentifierNamespaceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    is_active: bool | None = None
    row_version: int | None = None


class IdentifierTypeListItem(IdentifierNamespaceListItem):
    is_barcode: bool | None = None


class IdentifierNamespaceDetail(IdentifierNamespaceListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class IdentifierTypeDetail(IdentifierNamespaceDetail):
    is_barcode: bool | None = None


class IdentifierNamespaceQuery(ListQuery):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    is_active: bool | None = None


class IdentifierTypeQuery(IdentifierNamespaceQuery):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    is_barcode: bool | None = None
