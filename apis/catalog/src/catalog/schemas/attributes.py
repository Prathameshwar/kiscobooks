"""Native attribute wire values, exact integer/decimal transport and template inputs."""

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
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

from catalog.domain.attributes import AttributeValue, DefinitionRules
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import Dimension, ExpectedVersion

ValueType = Literal["TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE"]
VALUE_FIELDS = {
    "TEXT": "value_text",
    "INTEGER": "value_integer",
    "DECIMAL": "value_decimal",
    "BOOLEAN": "value_boolean",
    "DATE": "value_date",
}


class AttributeDefinitionCreate(MasterInput):
    value_type: ValueType
    measurement_dimension: Dimension | None = None
    is_variant_capable: StrictBool = False

    @model_validator(mode="after")
    def supported_definition(self) -> AttributeDefinitionCreate:
        DefinitionRules(self.value_type, self.measurement_dimension, self.is_variant_capable)
        return self


class AttributeDefinitionUpdate(MasterUpdate):
    value_type: ValueType | None = None
    measurement_dimension: Dimension | None = None
    is_variant_capable: StrictBool | None = None


class AttributeDefinitionListItem(MasterListItem):
    value_type: ValueType | None = None
    measurement_dimension: Dimension | None = None
    is_variant_capable: bool | None = None


class AttributeDefinitionDetail(AttributeDefinitionListItem, DetailFields):
    pass


class AttributeDefinitionQuery(MasterQuery):
    value_type: ValueType | None = None
    measurement_dimension: Dimension | None = None
    is_variant_capable: bool | None = None


class TypedValueFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value_text: str | None = Field(default=None, min_length=1, max_length=200)
    value_integer: int | None = Field(default=None, ge=-(2**63), lt=2**63)
    value_decimal: Decimal | None = None
    value_boolean: StrictBool | None = None
    value_date: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    unit_id: uuid.UUID | None = None

    @field_validator("value_integer", mode="before", json_schema_input_type=str | None)
    @classmethod
    def exact_integer(cls, value: Any) -> int | None:
        if value is None or type(value) is int:
            return value
        if not isinstance(value, str) or re.fullmatch(r"-?(0|[1-9][0-9]{0,18})", value) is None:
            raise ValueError("integer attribute requires an exact integer string")
        return int(value)

    @field_serializer("value_integer", when_used="json")
    def integer_transport(self, value: int | None) -> str | None:
        return str(value) if value is not None else None

    @field_validator("value_decimal", mode="before", json_schema_input_type=str | None)
    @classmethod
    def exact_number(cls, value: Any) -> Decimal | None:
        return exact_decimal(value) if value is not None else None


class AttributeOptionCreate(MasterInput, TypedValueFields):
    definition_id: uuid.UUID
    value_type: ValueType

    @model_validator(mode="after")
    def exactly_one_value(self) -> AttributeOptionCreate:
        present = {name for name in VALUE_FIELDS.values() if getattr(self, name) is not None}
        if present != {VALUE_FIELDS[self.value_type]}:
            raise ValueError("attribute option requires exactly its declared typed value")
        AttributeValue(self.value_type, getattr(self, VALUE_FIELDS[self.value_type]), self.unit_id)
        return self


class AttributeOptionUpdate(MasterUpdate, TypedValueFields):
    pass


class AttributeOptionListItem(MasterListItem):
    definition_id: uuid.UUID | None = None
    value_type: ValueType | None = None


class AttributeOptionDetail(AttributeOptionListItem, DetailFields, TypedValueFields):
    pass


class AttributeOptionQuery(MasterQuery):
    definition_id: uuid.UUID | None = None
    value_type: ValueType | None = None


class AttributeSetCreate(MasterInput):
    pass


class AttributeSetUpdate(MasterUpdate):
    pass


class AttributeSetListItem(MasterListItem):
    pass


class AttributeSetDetail(AttributeSetListItem, DetailFields):
    pass


class AttributeSetQuery(MasterQuery):
    pass


class AttributeMemberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition_id: uuid.UUID
    position: int = Field(ge=0, lt=128, strict=True)
    is_required: StrictBool = False
    allow_variant_axis: StrictBool = False


class AttributeSetRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    members: tuple[AttributeMemberInput, ...] = Field(default=(), max_length=128)


class AttributeSetRevisionUpdate(ExpectedVersion):
    members: tuple[AttributeMemberInput, ...] = Field(max_length=128)


class AttributeSetRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    attribute_set_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    published_at: dt.datetime | None = None


class AttributeSetRevisionDetail(AttributeSetRevisionListItem, DetailFields):
    pass


class AttributeSetRevisionQuery(ListQuery):
    published: bool | None = None


class AttributeMemberListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    revision_id: uuid.UUID | None = None
    definition_id: uuid.UUID | None = None
    position: int | None = None
    is_required: bool | None = None
    allow_variant_axis: bool | None = None


class AttributeMemberQuery(ListQuery):
    definition_id: uuid.UUID | None = None
    is_required: bool | None = None
    allow_variant_axis: bool | None = None
