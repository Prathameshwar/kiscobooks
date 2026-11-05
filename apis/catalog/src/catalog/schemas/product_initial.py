"""Bounded initial master setup; inventory movements are deliberately excluded."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from catalog.schemas.pricing import ExactDecimal
from catalog.schemas.product_authoring import (
    BarcodeInput,
    CategorySelection,
    FamilyAttributesInput,
    ManufacturerAssignmentInput,
    UnitBindingInput,
)


class InitialTax(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    directions: list[Literal["SALE", "PURCHASE"]] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def selected(self) -> "InitialTax":
        if self.classification_id is None and self.rule_id is None:
            raise ValueError("select a tax classification or rule")
        if len(set(self.directions)) != len(self.directions):
            raise ValueError("tax directions must be unique")
        return self


class InitialPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: uuid.UUID
    amount: ExactDecimal = Field(ge=0)
    price_basis_quantity: ExactDecimal = Field(gt=0)
    price_decimal_places: int = Field(strict=True, ge=0, le=4)


class InitialProductSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    group_id: uuid.UUID | None = None
    units: list[UnitBindingInput] = Field(default_factory=list, max_length=8)
    barcodes: list[BarcodeInput] = Field(default_factory=list, max_length=8)
    attributes: FamilyAttributesInput | None = None
    categories: list[CategorySelection] = Field(default_factory=list, max_length=128)
    manufacturer: ManufacturerAssignmentInput | None = None
    batch_enabled: StrictBool | None = None
    tax: InitialTax | None = None
    prices: list[InitialPrice] = Field(default_factory=list, max_length=65)
    expected_generation: int | None = Field(default=None, strict=True, ge=1)
    expected_source_version: int | None = Field(default=None, strict=True, ge=1)
    configuration_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def initial_versions(self) -> "InitialProductSetup":
        entries = [*self.units, *self.barcodes]
        if self.attributes is not None:
            entries.append(self.attributes)
        if self.manufacturer is not None and self.manufacturer.expected_version != 1:
            raise ValueError("initial manufacturer refers only to the new product version")
        if any(entry.expected_version != 1 for entry in entries):
            raise ValueError("initial setup refers only to the new product version")
        if any(entry.binding_id is not None for entry in self.barcodes):
            raise ValueError("initial barcodes use the new SKU, not an existing unit binding")
        if (self.tax is not None or self.prices or self.configuration_fingerprint is not None) and (
            self.expected_generation is None or self.expected_source_version is None
        ):
            raise ValueError("tax and pricing require reviewed configuration versions")
        if len({price.plan_id for price in self.prices}) != len(self.prices):
            raise ValueError("initial price plans must be unique")
        return self
