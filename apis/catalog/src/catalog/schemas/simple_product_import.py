"""Flat business columns and bounded progress for Simple product imports."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from billing_platform.import_contracts import ImportDetail
from pydantic import Field, field_validator

from catalog.schemas.configuration import StrictInput
from catalog.schemas.pricing import ExactDecimal
from catalog.schemas.simple_products import CODE


class SimpleImportRow(StrictInput):
    name: str = Field(min_length=1, max_length=100, title="Product name")
    code: str | None = Field(
        default=None, max_length=30, pattern=CODE, title="Product code (optional)"
    )
    kind: Literal["GOODS", "SERVICE"] = Field(default="GOODS", title="Type")
    group: str | None = Field(default=None, max_length=100, title="Product group code")
    base_unit: str = Field(min_length=1, max_length=30, title="Base unit code")
    hsn_sac: str | None = Field(default=None, max_length=8, title="HSN/SAC code")
    gst_rule: str | None = Field(default=None, max_length=30, title="GST treatment / rate code")
    purchase_price: ExactDecimal | None = Field(default=None, ge=0, title="Purchase price")
    sale_price: ExactDecimal | None = Field(default=None, ge=0, title="Selling price")
    mrp: ExactDecimal | None = Field(default=None, gt=0, title="MRP")
    opening_quantity: ExactDecimal = Field(default=Decimal("0"), ge=0, title="Opening quantity")
    opening_date: dt.date | None = Field(default=None, title="Opening date (books begin date)")
    brand: str | None = Field(default=None, max_length=30, title="Brand code")
    brand_series: str | None = Field(default=None, max_length=30, title="Brand series code")
    model_code: str | None = Field(default=None, max_length=100, title="Model")
    barcode_value: str | None = Field(
        default=None, min_length=1, max_length=128, title="Barcode value"
    )
    barcode_symbology: Literal["CODE128", "GTIN", "QR"] | None = Field(
        default=None,
        title="Barcode format",
        description=(
            "Blank uses CODE128 when a barcode value is entered. GTIN validates its check digit."
        ),
    )
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    shared_custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator(
        "code", "group", "base_unit", "hsn_sac", "gst_rule", "brand", "brand_series", mode="before"
    )
    @classmethod
    def normalize_reference(cls, value: Any) -> Any:
        return value.strip().upper() or None if isinstance(value, str) else value

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"SERVICES": "SERVICE"}.get(value.strip().upper(), value.strip().upper())
        return value

    @field_validator("barcode_symbology", mode="before")
    @classmethod
    def normalize_barcode_format(cls, value: Any) -> Any:
        return value.strip().upper() or None if isinstance(value, str) else value


class SimpleImportProgress(StrictInput):
    job: ImportDetail
    pending_count: int = Field(ge=0, le=200)
    failed_count: int = Field(ge=0, le=200)
    can_resume: bool


class SimpleImportRowResult(StrictInput):
    id: uuid.UUID
    key: str
    source_file: str
    source_sheet: str
    source_row: int
    code: str | None = None
    name: str | None = None
    state: str
    step: str | None = None
    item_id: uuid.UUID | None = None
    opening_posted: bool = False
    messages: list[dict[str, str]] = Field(default_factory=list, max_length=100)
