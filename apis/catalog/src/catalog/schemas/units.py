"""Unit wire types and lean list contract, ready for source-gated master APIs."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import Decimal
from typing import Any, Literal

from billing_platform.exact import exact_decimal
from billing_platform.listing import ListQuery
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from catalog.domain.units import QuantityRule

type Dimension = Literal["COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"]


class UnitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    dimension: Dimension
    decimal_places: int = Field(ge=0, le=4, strict=True)
    quantity_increment: Decimal

    @field_validator("quantity_increment", mode="before", json_schema_input_type=str)
    @classmethod
    def exact_increment(cls, value: Any) -> Decimal:
        return exact_decimal(value)

    @field_validator("name", "symbol")
    @classmethod
    def meaningful_label(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("label must contain printable text")
        return value.strip()

    @model_validator(mode="after")
    def quantity_rule(self) -> UnitCreate:
        QuantityRule(self.decimal_places, self.quantity_increment)
        return self


class UnitListItem(BaseModel):
    """Denied fields are omitted, never replaced with fabricated values."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    code: str | None = None
    symbol: str | None = None
    name: str | None = None
    dimension: Dimension | None = None
    decimal_places: int | None = None
    quantity_increment: Decimal | None = None
    is_active: bool | None = None
    row_version: int | None = None


class UnitDetail(UnitListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class UnitListQuery(ListQuery):
    dimension: Dimension | None = None
    is_active: bool | None = None
    code: str | None = Field(default=None, min_length=1, max_length=30)


class UnitConversionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_unit_id: uuid.UUID
    canonical_unit_id: uuid.UUID
    numerator: int = Field(ge=1, le=2**63 - 1, strict=True)
    denominator: int = Field(ge=1, le=2**63 - 1, strict=True)

    @field_validator("numerator", "denominator", mode="before", json_schema_input_type=str)
    @classmethod
    def exact_ratio_part(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not re.fullmatch(r"[1-9][0-9]{0,18}", value):
                raise ValueError("ratio part requires a positive integer string")
            return int(value)
        return value


class UnitTaxCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: uuid.UUID
    jurisdiction: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    official_code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    valid_from: dt.date
    valid_to: dt.date | None = None

    @model_validator(mode="after")
    def date_order(self) -> UnitTaxCodeInput:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        return self


class PackTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        return UnitCreate.meaningful_label(value)


class ExpectedVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)


class UnitUpdate(ExpectedVersion):
    code: str | None = Field(
        default=None, min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$"
    )
    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    dimension: Dimension | None = None
    decimal_places: int | None = Field(default=None, ge=0, le=4, strict=True)
    quantity_increment: Decimal | None = None

    @field_validator("quantity_increment", mode="before", json_schema_input_type=str)
    @classmethod
    def exact_increment(cls, value: Any) -> Decimal:
        return exact_decimal(value)

    @model_validator(mode="after")
    def no_null_updates(self) -> UnitUpdate:
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("unit fields cannot be cleared")
        return self


class PackTypeUpdate(ExpectedVersion):
    code: str | None = Field(
        default=None, min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$"
    )
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def no_null_updates(self) -> PackTypeUpdate:
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("pack type fields cannot be cleared")
        return self


class PackTypeListQuery(ListQuery):
    is_active: bool | None = None
    code: str | None = Field(default=None, min_length=1, max_length=30)


class PackTypeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    is_active: bool | None = None
    row_version: int | None = None


class PackTypeDetail(PackTypeListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class UnitConversionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    from_unit_id: uuid.UUID | None = None
    canonical_unit_id: uuid.UUID | None = None
    numerator: int | None = None
    denominator: int | None = None

    @field_serializer("numerator", "denominator")
    def ratio_wire(self, value: int | None) -> str | None:
        return str(value) if value is not None else None


class UnitConversionDetail(UnitConversionListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class UnitConversionQuery(ListQuery):
    from_unit_id: uuid.UUID | None = None
    canonical_unit_id: uuid.UUID | None = None


class UnitTaxCodeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    unit_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    official_code: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class UnitTaxCodeDetail(UnitTaxCodeListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class UnitTaxCodeQuery(ListQuery):
    unit_id: uuid.UUID | None = None
    jurisdiction: str | None = Field(default=None, min_length=1, max_length=30)
    valid_at: dt.date | None = None


class UnitTaxCodeClose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_valid_to: dt.date | None
    valid_to: dt.date


class UnitConvertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_unit_id: uuid.UUID
    to_unit_id: uuid.UUID
    quantity: Decimal

    @field_validator("quantity", mode="before", json_schema_input_type=str)
    @classmethod
    def exact_quantity(cls, value: Any) -> Decimal:
        result = exact_decimal(value)
        if result < 0:
            raise ValueError("quantity cannot be negative")
        return result


class UnitConvertResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_unit_id: uuid.UUID
    to_unit_id: uuid.UUID
    input_quantity: Decimal
    quantity: Decimal
