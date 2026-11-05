"""One user action for a simple product and its optional first stock entry."""

import datetime as dt
import unicodedata
import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator
from voucher_execution.identifiers import IdentifierInput, IdentifierRequirement

from catalog.schemas.configuration import EffectiveConfiguration, StrictInput
from catalog.schemas.field_metadata import FieldMetadata
from catalog.schemas.pricing import ExactDecimal
from catalog.schemas.product_authoring import CategorySelection
from catalog.schemas.product_initial import InitialTax
from catalog.schemas.simple_products import CODE, SimpleProductFieldSet


class SimpleCreationBarcode(StrictInput):
    value: str = Field(min_length=1, max_length=128)
    symbology: Literal["GTIN", "CODE128", "QR"] = "CODE128"


class SimpleSalePrice(StrictInput):
    price_level_id: uuid.UUID
    amount: ExactDecimal = Field(ge=0)


class SimpleSalePriceOption(StrictInput):
    price_level_id: uuid.UUID
    plan_id: uuid.UUID
    code: str
    name: str
    ordinal: int = Field(ge=1, le=64)
    tax_basis: Literal["EXCLUSIVE", "INCLUSIVE"]
    required: bool
    is_default: bool


class SimpleSerialInput(StrictInput):
    identifiers: list[IdentifierInput] = Field(min_length=1, max_length=16)


class SimpleSerialOptions(StrictInput):
    enabled: bool = False
    requirements: list[IdentifierRequirement] = Field(default_factory=list, max_length=2)


class SimpleBatchInput(StrictInput):
    code: str = Field(min_length=1, max_length=100)
    manufactured_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    expires_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    opening_quantity: ExactDecimal = Field(default=Decimal("0"), ge=0)
    purchase_price: ExactDecimal | None = Field(default=None, ge=0)
    sale_price: ExactDecimal | None = Field(default=None, ge=0)
    sale_prices: list[SimpleSalePrice] = Field(default_factory=list, max_length=64)
    mrp: ExactDecimal | None = Field(default=None, gt=0)
    serials: list[SimpleSerialInput] = Field(default_factory=list, max_length=200)

    @field_validator("code")
    @classmethod
    def printable_code(cls, value: str) -> str:
        value = value.strip()
        if not value or any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Enter a printable batch number")
        if len(unicodedata.normalize("NFKC", value).casefold()) > 100:
            raise ValueError("Batch number exceeds 100 normalized characters")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.opening_quantity and self.purchase_price is None:
            raise ValueError("Purchase price is required for batch opening stock")
        if self.sale_prices and self.sale_price is not None:
            raise ValueError("Use either Selling price or per-level selling prices")
        if len({entry.price_level_id for entry in self.sale_prices}) != len(self.sale_prices):
            raise ValueError("Selling-price levels must be distinct")
        if self.manufactured_on and self.expires_on and self.expires_on < self.manufactured_on:
            raise ValueError("Expiry must not precede manufacture")
        return self


class SimpleBatchOptions(StrictInput):
    available: bool = False
    required: bool = False
    expiry_enabled: bool = False
    expiry_required: bool = False
    manufacture_date_required: bool = False


class SimpleCreationInput(StrictInput):
    kind: Literal["GOODS", "SERVICE"] = "GOODS"
    name: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=30, pattern=CODE)
    group_id: uuid.UUID | None = None
    base_unit_id: uuid.UUID
    tax: InitialTax | None = None
    purchase_price: ExactDecimal | None = Field(default=None, ge=0)
    sale_price: ExactDecimal | None = Field(default=None, ge=0)
    sale_prices: list[SimpleSalePrice] = Field(default_factory=list, max_length=64)
    mrp: ExactDecimal | None = Field(default=None, gt=0)
    opening_quantity: ExactDecimal = Field(default=Decimal("0"), ge=0)
    opening_date: dt.date | None = None
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = Field(default=None, min_length=1, max_length=100)
    barcode: SimpleCreationBarcode | None = None
    categories: list[CategorySelection] = Field(default_factory=list, max_length=128)
    manufacturer_id: uuid.UUID | None = None
    manufacturer_site_id: uuid.UUID | None = None
    batch_enabled: StrictBool | None = None
    batches: list[SimpleBatchInput] = Field(default_factory=list, max_length=64)
    serials: list[SimpleSerialInput] = Field(default_factory=list, max_length=200)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    shared_custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("name")
    @classmethod
    def name_is_printable(cls, value: str) -> str:
        from catalog.schemas.item_input import ItemInput

        return ItemInput.label(value)

    @field_validator("code", mode="before")
    @classmethod
    def blank_code(cls, value: Any) -> Any:
        return value.strip().upper() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def opening_matches_kind(self) -> Self:
        serial_count = len(self.serials) + sum(len(row.serials) for row in self.batches)
        if serial_count > 200:
            raise ValueError("Capture up to 200 serial units in one product opening")
        if self.kind == "SERVICE" and serial_count:
            raise ValueError("Services cannot have serial units")
        if self.batch_enabled and self.serials:
            raise ValueError("Enter serial units on their batch rows")
        if self.kind == "SERVICE" and (self.batch_enabled is not None or self.batches):
            raise ValueError("Services cannot have batches")
        if self.batches and not self.batch_enabled:
            raise ValueError("Enable batches before entering batch rows")
        if self.batch_enabled and (
            self.opening_quantity
            or self.purchase_price is not None
            or self.sale_price is not None
            or self.sale_prices
            or self.mrp is not None
        ):
            raise ValueError("Enter opening quantities and prices on batch rows")
        if len({unicodedata.normalize("NFKC", row.code).casefold() for row in self.batches}) != len(
            self.batches
        ):
            raise ValueError("Batch numbers must be distinct")
        if self.sale_prices and self.sale_price is not None:
            raise ValueError("use either Selling price or per-level selling prices")
        if len({price.price_level_id for price in self.sale_prices}) != len(self.sale_prices):
            raise ValueError("selling-price levels must be unique")
        if self.kind == "SERVICE" and (self.opening_quantity or self.opening_date is not None):
            raise ValueError("services cannot have opening stock")
        if self.opening_quantity and self.purchase_price is None:
            raise ValueError(
                "Purchase price is required when opening quantity is greater than zero"
            )
        if self.series_id is not None and self.brand_id is None:
            raise ValueError("brand series requires its brand")
        if self.manufacturer_site_id is not None and self.manufacturer_id is None:
            raise ValueError("manufacturer site requires its manufacturer")
        if self.kind == "SERVICE" and self.manufacturer_id is not None:
            raise ValueError("services cannot have physical manufacturer assignments")
        if len({entry.category_id for entry in self.categories}) != len(self.categories):
            raise ValueError("category memberships must be distinct")
        if self.tax is not None and set(self.tax.directions) != {"SALE", "PURCHASE"}:
            raise ValueError("simple products apply the selected GST setup to sale and purchase")
        return self

    @property
    def has_opening(self) -> bool:
        return bool(self.opening_quantity or any(row.opening_quantity for row in self.batches))


class SimpleCreationStatus(StrictInput):
    id: uuid.UUID
    company_id: uuid.UUID
    status: Literal["RUNNING", "COMPLETE"]
    step: str
    code: str
    item_id: uuid.UUID | None
    row_version: int
    opening_posted: bool
    can_edit: bool = False


class SimpleCreationRevision(StrictInput):
    expected_version: int = Field(ge=1)
    product: SimpleCreationInput


class SimpleRequiredCategoryScheme(StrictInput):
    id: uuid.UUID
    name: str
    membership_mode: Literal["SINGLE", "MULTIPLE"]


class SimpleCreationOptions(StrictInput):
    company_id: uuid.UUID
    kind: Literal["GOODS", "SERVICE"]
    today: dt.date
    opening_date: dt.date
    currency: str
    field_set: SimpleProductFieldSet
    configuration: EffectiveConfiguration
    default_group_id: uuid.UUID | None
    inventory_enabled: bool
    gst_enabled: bool
    fields: list[FieldMetadata] = Field(default_factory=list)
    sale_price_levels: list[SimpleSalePriceOption] = Field(default_factory=list, max_length=64)
    required_category_schemes: list[SimpleRequiredCategoryScheme] = Field(
        default_factory=list, max_length=128
    )
    batch: SimpleBatchOptions = Field(default_factory=SimpleBatchOptions)
    serial: SimpleSerialOptions = Field(default_factory=SimpleSerialOptions)
