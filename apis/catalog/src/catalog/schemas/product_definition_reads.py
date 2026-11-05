"""Lean product child lists and separately protected native details."""

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class FamilyGroupAssignmentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    family_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class FamilyGroupAssignmentDetail(FamilyGroupAssignmentListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class FamilyCategoryListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    family_id: uuid.UUID | None = None
    scheme_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    is_primary: bool | None = None
    primary_slot: int | None = None


class FamilyCategoryDetail(FamilyCategoryListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class FamilyManufacturerListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    family_id: uuid.UUID | None = None
    manufacturer_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    production_role: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class FamilyManufacturerDetail(FamilyManufacturerListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class FamilyAttributeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    family_id: uuid.UUID | None = None
    definition_id: uuid.UUID | None = None
    is_axis: bool | None = None
    is_required: bool | None = None
    position: int | None = None


class FamilyAttributeDetail(FamilyAttributeListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class FamilyAttributeOptionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    family_id: uuid.UUID | None = None
    definition_id: uuid.UUID | None = None
    option_id: uuid.UUID | None = None


class FamilyAttributeOptionDetail(FamilyAttributeOptionListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class ItemAttributeValueListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    definition_id: uuid.UUID | None = None
    option_id: uuid.UUID | None = None
    value_type: str | None = None
    unit_id: uuid.UUID | None = None


class ItemAttributeValueDetail(ItemAttributeValueListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    value_text: str | None = None
    value_integer: int | None = None
    value_decimal: Decimal | None = None
    value_boolean: bool | None = None
    value_date: dt.date | None = None

    @field_serializer("value_integer", when_used="json")
    def integer_transport(self, value: int | None) -> str | None:
        return None if value is None else str(value)


class ItemUnitBindingListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    code: str | None = None
    unit_id: uuid.UUID | None = None
    usage_role: str | None = None


class ItemUnitBindingDetail(ItemUnitBindingListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class ItemBarcodeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    binding_id: uuid.UUID | None = None
    value: str | None = None
    symbology: str | None = None
    is_active: bool | None = None


class ItemBarcodeDetail(ItemBarcodeListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class ProductConfigurationAdoptionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    revision: int | None = None
    effective_on: dt.date | None = None
    product_type_revision_id: uuid.UUID | None = None
    group_assignment_id: uuid.UUID | None = None
    source_version: int | None = None
    policy_generation: int | None = None
    resolution_version: int | None = None


class ProductConfigurationAdoptionDetail(ProductConfigurationAdoptionListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class ItemUnitRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    binding_id: uuid.UUID | None = None
    revision: int | None = None
    pack_type_id: uuid.UUID | None = None
    conversion_mode: str | None = None
    numerator: int | None = None
    denominator: int | None = None
    nominal_ratio: Decimal | None = None
    secondary_unit_id: uuid.UUID | None = None
    quantity_decimal_places: int | None = None
    quantity_increment: Decimal | None = None
    fractional_entry: bool | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None

    @field_serializer("numerator", "denominator")
    def ratio_transport(self, value: int | None) -> str | None:
        return None if value is None else str(value)


class ItemUnitRevisionDetail(ItemUnitRevisionListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class ProductConfigurationAdoptionSourceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    adoption_id: uuid.UUID | None = None
    scope_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None


class ProductConfigurationAdoptionSourceDetail(ProductConfigurationAdoptionSourceListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
