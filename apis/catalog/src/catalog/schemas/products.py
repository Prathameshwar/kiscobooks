"""Strict product authoring and lean SKU browse contracts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from billing_platform.custom_query import CustomPredicate
from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from catalog.schemas.classification import MasterInput, MasterQuery
from catalog.schemas.configuration import DefaultsAcceptance
from catalog.schemas.item_input import ItemInput
from catalog.schemas.product_initial import InitialProductSetup
from catalog.schemas.units import ExpectedVersion

Status = Literal["DRAFT", "ACTIVE", "DISCONTINUED"]


class FamilyCreate(MasterInput):
    initial_setup: InitialProductSetup | None = None
    accept_defaults: DefaultsAcceptance | None = None
    kind: Literal["GOODS", "SERVICE"]
    product_type_revision_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    default_item: ItemInput

    @model_validator(mode="after")
    def series_brand(self) -> Self:
        if self.series_id is not None and self.brand_id is None:
            raise ValueError("series requires its brand")
        return self


class FamilyPatch(ExpectedVersion):
    code: str | None = Field(
        default=None, min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$"
    )
    name: str | None = Field(default=None, min_length=1, max_length=100)
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("name")
    @classmethod
    def label(cls, value: str | None) -> str | None:
        return None if value is None else ItemInput.label(value)

    @model_validator(mode="after")
    def nonnull_identity(self) -> Self:
        if any(
            key in self.model_fields_set and getattr(self, key) is None for key in ("code", "name")
        ):
            raise ValueError("product labels cannot be cleared")
        return self


class ItemPatch(ExpectedVersion):
    sku: str | None = Field(
        default=None, min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$"
    )
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sellable: StrictBool | None = None
    purchasable: StrictBool | None = None
    min_sale_quantity: Decimal | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("name")
    @classmethod
    def label(cls, value: str | None) -> str | None:
        return FamilyPatch.label(value)

    @field_validator("min_sale_quantity", mode="before", json_schema_input_type=str | None)
    @classmethod
    def quantity(cls, value: Any) -> Decimal | None:
        return ItemInput.quantity(value)

    @model_validator(mode="after")
    def nonnull_fields(self) -> Self:
        if any(
            key in self.model_fields_set and getattr(self, key) is None
            for key in ("sku", "name", "sellable", "purchasable")
        ):
            raise ValueError("SKU identity and operation flags cannot be cleared")
        return self


class FamilyListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    kind: Literal["GOODS", "SERVICE"] | None = None
    structure_mode: Literal["SIMPLE", "VARIANT"] | None = None
    status: Status | None = None
    row_version: int | None = None
    product_type_revision_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None


class FamilyDetail(FamilyListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    policy_generation: int
    model_code: str | None = None
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ItemListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    family_id: uuid.UUID | None = None
    sku: str | None = None
    name: str | None = None
    base_unit_id: uuid.UUID | None = None
    status: Status | None = None
    sellable: bool | None = None
    purchasable: bool | None = None
    row_version: int | None = None


class ItemDetail(ItemListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    policy_generation: int
    default_slot: int | None = None
    min_sale_quantity: Decimal | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ProductCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family: FamilyDetail
    default_item: ItemDetail
    price_draft_ids: list[uuid.UUID] = Field(default_factory=list, max_length=65)


class ProductQuery(ListQuery):
    custom_filters: str | None = Field(default=None, max_length=4096)

    def predicates(self) -> list[CustomPredicate]:
        return MasterQuery(custom_filters=self.custom_filters).predicates()


class FamilyQuery(ProductQuery):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    kind: Literal["GOODS", "SERVICE"] | None = None
    status: Status | None = None
    product_type_revision_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None


class ItemQuery(ProductQuery):
    sku: str | None = Field(default=None, min_length=1, max_length=30)
    family_id: uuid.UUID | None = None
    base_unit_id: uuid.UUID | None = None
    status: Status | None = None
    sellable: bool | None = None
    purchasable: bool | None = None
