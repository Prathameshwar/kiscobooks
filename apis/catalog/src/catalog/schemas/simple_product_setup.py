"""Product-owned access to native family children without duplicate identity inputs."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from catalog.schemas.attribute_forms import AttributeFormField
from catalog.schemas.configuration import StrictInput
from catalog.schemas.product_authoring import (
    AttributeSelection,
    CategorySelection,
    FamilyAttributeInput,
)


class ProductSetupGuard(StrictInput):
    revision: str = Field(min_length=1, max_length=8192)
    authoring_version: int = Field(strict=True, ge=0, lt=2**31)


class ProductGroupInput(ProductSetupGuard):
    group_id: uuid.UUID
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class ProductManufacturerInput(ProductSetupGuard):
    manufacturer_id: uuid.UUID
    site_id: uuid.UUID | None = None
    role: Literal["MANUFACTURER", "ASSEMBLER", "IMPORTER"] = "MANUFACTURER"
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("manufacturer dates are reversed")
        return self


class ProductCategoriesInput(ProductSetupGuard):
    categories: list[CategorySelection] = Field(max_length=128)
    valid_from: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    preview_token: str | None = Field(default=None, min_length=1, max_length=8192)


class ProductAttributesInput(ProductSetupGuard):
    attributes: list[FamilyAttributeInput] = Field(max_length=128)
    values: list[AttributeSelection] = Field(default_factory=list, max_length=128)


class SimpleProductAttributeForm(ProductSetupGuard):
    id: uuid.UUID
    name: str
    status: str
    base_unit_id: uuid.UUID
    base_unit_label: str
    can_configure: bool
    fields: list[AttributeFormField] = Field(max_length=128)


class SimpleProductCategoryPreview(ProductSetupGuard):
    id: uuid.UUID
    preview_token: str
    membership_count: int
    closing_count: int
