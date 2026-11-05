"""Commercial master inputs, protected detail and dedicated lean list contracts."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from catalog.schemas.classification import (
    DetailFields,
    Kind,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import Dimension, ExpectedVersion

InventoryMode = Literal["NON_STOCK", "STOCK"]
TrackingMode = Literal["NONE", "BATCH", "SERIAL", "BATCH_SERIAL"]
ProductionRole = Literal["OEM", "CONTRACT_MANUFACTURER", "ASSEMBLER"]


class CustomMasterInput(MasterInput):
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)


class CustomMasterUpdate(MasterUpdate):
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)


class BrandCreate(CustomMasterInput):
    parent_brand_id: uuid.UUID | None = None
    owner_party_id: uuid.UUID | None = None


class BrandUpdate(CustomMasterUpdate):
    owner_party_id: uuid.UUID | None = None


class BrandReparent(ExpectedVersion):
    expected_generation: int = Field(ge=1, strict=True)
    parent_brand_id: uuid.UUID | None


class ManufacturerCreate(CustomMasterInput):
    party_id: uuid.UUID | None = None


class ManufacturerUpdate(CustomMasterUpdate):
    party_id: uuid.UUID | None = None


class BrandSeriesCreate(MasterInput):
    brand_id: uuid.UUID


class BrandSeriesUpdate(MasterUpdate):
    pass


class ManufacturerSiteCreate(MasterInput):
    manufacturer_id: uuid.UUID
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(default=None, min_length=1, max_length=6)


class ManufacturerSiteUpdate(MasterUpdate):
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(default=None, min_length=1, max_length=6)


class ProductTypeCreate(CustomMasterInput):
    kind: Kind


class ProductTypeUpdate(CustomMasterUpdate):
    kind: Kind | None = None


class BrandListItem(MasterListItem):
    parent_brand_id: uuid.UUID | None = None


class BrandDetail(BrandListItem, DetailFields):
    owner_party_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ManufacturerListItem(MasterListItem):
    pass


class ManufacturerDetail(ManufacturerListItem, DetailFields):
    party_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class BrandSeriesListItem(MasterListItem):
    brand_id: uuid.UUID | None = None


class BrandSeriesDetail(BrandSeriesListItem, DetailFields):
    pass


class ManufacturerSiteListItem(MasterListItem):
    manufacturer_id: uuid.UUID | None = None
    country_code: str | None = None
    state_code: str | None = None


class ManufacturerSiteDetail(ManufacturerSiteListItem, DetailFields):
    pass


class ProductTypeListItem(MasterListItem):
    kind: Kind | None = None


class ProductTypeDetail(ProductTypeListItem, DetailFields):
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class BrandQuery(MasterQuery):
    parent_brand_id: uuid.UUID | None = None


class ManufacturerQuery(MasterQuery):
    pass


class BrandSeriesQuery(MasterQuery):
    brand_id: uuid.UUID | None = None


class ManufacturerSiteQuery(MasterQuery):
    manufacturer_id: uuid.UUID | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(default=None, min_length=1, max_length=6)


class ProductTypeQuery(MasterQuery):
    kind: Kind | None = None


class BrandManufacturerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_id: uuid.UUID
    manufacturer_id: uuid.UUID
    production_role: ProductionRole
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = None

    @model_validator(mode="after")
    def date_order(self) -> "BrandManufacturerCreate":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("relationship end precedes its start")
        return self


class BrandManufacturerClose(ExpectedVersion):
    valid_to: dt.date = Field(ge=dt.date(1000, 1, 1))


class BrandManufacturerListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    manufacturer_id: uuid.UUID | None = None
    production_role: ProductionRole | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    row_version: int | None = None


class BrandManufacturerDetail(BrandManufacturerListItem, DetailFields):
    pass


class BrandManufacturerQuery(ListQuery):
    brand_id: uuid.UUID | None = None
    manufacturer_id: uuid.UUID | None = None
    production_role: ProductionRole | None = None
    valid_at: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class TypeRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory_modes: tuple[InventoryMode, ...] = Field(min_length=1, max_length=2)
    tracking_modes: tuple[TrackingMode, ...] = Field(min_length=1, max_length=4)
    unit_dimensions: tuple[Dimension, ...] = Field(min_length=1, max_length=7)
    allow_variants: StrictBool = True
    require_brand: StrictBool = False
    require_manufacturer: StrictBool = False
    require_expiry: StrictBool = False
    attribute_set_revision_id: uuid.UUID | None = None
    inventory_template_revision_id: uuid.UUID | None = None
    warranty_revision_id: uuid.UUID | None = None
    return_policy_revision_id: uuid.UUID | None = None
    handling_revision_id: uuid.UUID | None = None

    @field_validator("inventory_modes", "tracking_modes", "unit_dimensions")
    @classmethod
    def distinct_options(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("requirement options cannot repeat")
        return tuple(sorted(value))


class TypeRevisionUpdate(ExpectedVersion):
    inventory_modes: tuple[InventoryMode, ...] | None = Field(
        default=None, min_length=1, max_length=2
    )
    tracking_modes: tuple[TrackingMode, ...] | None = Field(
        default=None, min_length=1, max_length=4
    )
    unit_dimensions: tuple[Dimension, ...] | None = Field(default=None, min_length=1, max_length=7)
    allow_variants: StrictBool | None = None
    require_brand: StrictBool | None = None
    require_manufacturer: StrictBool | None = None
    require_expiry: StrictBool | None = None
    attribute_set_revision_id: uuid.UUID | None = None
    inventory_template_revision_id: uuid.UUID | None = None
    warranty_revision_id: uuid.UUID | None = None
    return_policy_revision_id: uuid.UUID | None = None
    handling_revision_id: uuid.UUID | None = None


class TypeRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    product_type_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    kind: Kind | None = None
    published_at: dt.datetime | None = None


class TypeRevisionDetail(TypeRevisionListItem, DetailFields):
    inventory_modes: tuple[InventoryMode, ...] | None = None
    tracking_modes: tuple[TrackingMode, ...] | None = None
    unit_dimensions: tuple[Dimension, ...] | None = None
    allow_variants: bool | None = None
    require_brand: bool | None = None
    require_manufacturer: bool | None = None
    require_expiry: bool | None = None
    attribute_set_revision_id: uuid.UUID | None = None
    inventory_template_revision_id: uuid.UUID | None = None
    warranty_revision_id: uuid.UUID | None = None
    return_policy_revision_id: uuid.UUID | None = None
    handling_revision_id: uuid.UUID | None = None


class TypeRevisionQuery(ListQuery):
    published: bool | None = None
