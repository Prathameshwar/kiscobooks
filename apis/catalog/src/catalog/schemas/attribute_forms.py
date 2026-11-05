"""Bounded, authorized product attribute authoring metadata."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from catalog.schemas.attributes import ValueType
from catalog.schemas.product_authoring import AttributeSelection
from catalog.schemas.units import Dimension


class AttributeFormOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    label: str
    is_active: bool


class AttributeFormField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition_id: uuid.UUID
    label: str
    value_type: ValueType
    measurement_dimension: Dimension | None
    is_variant_capable: bool
    is_active: bool
    is_axis: bool
    is_required: bool
    position: int
    allowed_options: list[AttributeFormOption] = Field(max_length=128)
    value: AttributeSelection | None
    option_label: str | None
    unit_label: str | None
    writable: bool
    variant_writable: bool


class ProductAttributeForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    item_version: int
    item_name: str
    item_status: str
    family_id: uuid.UUID
    family_version: int
    family_name: str
    family_status: str
    default_item_id: uuid.UUID
    structure_mode: str
    base_unit_id: uuid.UUID
    base_unit_label: str
    can_configure: bool
    can_create_variant: bool
    fields: list[AttributeFormField] = Field(max_length=128)
