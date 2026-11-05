"""One public product identity backed by the existing native family/item aggregate."""

import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from catalog.schemas.configuration import DefaultsAcceptance
from catalog.schemas.field_metadata import FieldMetadata
from catalog.schemas.item_input import ItemInput
from catalog.schemas.product_initial import InitialProductSetup
from catalog.schemas.products import FamilyPatch, ItemPatch, ProductQuery

CODE = r"^[A-Z0-9][A-Z0-9_.-]*$"


class SimpleProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authoring_version: int = Field(strict=True, ge=0, lt=2**31)
    code: str = Field(min_length=1, max_length=30, pattern=CODE)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["GOODS", "SERVICE"]
    product_type_revision_id: uuid.UUID
    base_unit_id: uuid.UUID
    sellable: StrictBool = True
    purchasable: StrictBool = True
    min_sale_quantity: Decimal | None = None
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    shared_custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    initial_setup: InitialProductSetup | None = None
    accept_defaults: DefaultsAcceptance | None = None

    @field_validator("name")
    @classmethod
    def label(cls, value: str) -> str:
        return ItemInput.label(value)

    @field_validator("min_sale_quantity", mode="before", json_schema_input_type=str | None)
    @classmethod
    def quantity(cls, value: Any) -> Decimal | None:
        return ItemInput.quantity(value)

    @model_validator(mode="after")
    def references(self) -> Self:
        if self.series_id is not None and self.brand_id is None:
            raise ValueError("series requires its brand")
        return self


class SimpleProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=1, max_length=8192)
    authoring_version: int = Field(strict=True, ge=0, lt=2**31)
    code: str | None = Field(default=None, min_length=1, max_length=30, pattern=CODE)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sellable: StrictBool | None = None
    purchasable: StrictBool | None = None
    min_sale_quantity: Decimal | None = None
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    shared_custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("name")
    @classmethod
    def label(cls, value: str | None) -> str | None:
        return None if value is None else ItemInput.label(value)

    @field_validator("min_sale_quantity", mode="before", json_schema_input_type=str | None)
    @classmethod
    def quantity(cls, value: Any) -> Decimal | None:
        return ItemInput.quantity(value)

    @model_validator(mode="after")
    def native_inputs(self) -> Self:
        supplied = self.model_dump(exclude_unset=True)
        ItemPatch.model_validate(
            {
                "expected_version": 1,
                **{
                    ("sku" if key == "code" else key): value
                    for key, value in supplied.items()
                    if key
                    in {
                        "code",
                        "name",
                        "sellable",
                        "purchasable",
                        "min_sale_quantity",
                        "custom_fields",
                    }
                },
            }
        )
        FamilyPatch.model_validate(
            {
                "expected_version": 1,
                **{
                    ("custom_fields" if key == "shared_custom_fields" else key): value
                    for key, value in supplied.items()
                    if key
                    in {
                        "name",
                        "brand_id",
                        "series_id",
                        "model_code",
                        "description",
                        "shared_custom_fields",
                    }
                },
            }
        )
        return self


class SimpleProductListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    base_unit_id: uuid.UUID | None = None
    status: Literal["DRAFT", "ACTIVE", "DISCONTINUED"] | None = None
    sellable: bool | None = None
    purchasable: bool | None = None


class SimpleProductDetail(SimpleProductListItem):
    company_id: uuid.UUID
    revision: str
    authoring_version: int
    policy_generation: int
    kind: Literal["GOODS", "SERVICE"] | None = None
    product_type_revision_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = None
    description: str | None = None
    min_sale_quantity: Decimal | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    shared_custom_fields: dict[str, Any] = Field(default_factory=dict)
    price_draft_ids: list[uuid.UUID] = Field(default_factory=list, max_length=65)
    related: dict[str, str] = Field(default_factory=dict, max_length=16)


class SimpleProductQuery(ProductQuery):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    base_unit_id: uuid.UUID | None = None
    status: Literal["DRAFT", "ACTIVE", "DISCONTINUED"] | None = None
    sellable: bool | None = None
    purchasable: bool | None = None


class SimpleProductFieldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    source_version: int
    authoring_version: int
    fields: list[FieldMetadata] = Field(max_length=512)
    native_bindings: dict[str, str] = Field(default_factory=dict, max_length=512)
