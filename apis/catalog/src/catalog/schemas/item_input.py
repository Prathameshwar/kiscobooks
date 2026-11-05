"""Shared strict SKU input for product creation and variant authoring."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.exact import exact_decimal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from catalog.schemas.units import UnitCreate


class ItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=100)
    base_unit_id: uuid.UUID
    sellable: StrictBool = True
    purchasable: StrictBool = True
    min_sale_quantity: Decimal | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("name")
    @classmethod
    def label(cls, value: str) -> str:
        return UnitCreate.meaningful_label(value)

    @field_validator("min_sale_quantity", mode="before", json_schema_input_type=str | None)
    @classmethod
    def quantity(cls, value: Any) -> Decimal | None:
        result = None if value is None else exact_decimal(value)
        if result is not None and result <= 0:
            raise ValueError("minimum sale quantity must be positive")
        return result
