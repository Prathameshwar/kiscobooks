"""Bounded native product authoring; arbitrary attributes never drive money."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from billing_platform.exact import exact_decimal
from billing_platform.listing import ListQuery
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

from catalog.schemas.attributes import TypedValueFields, ValueType
from catalog.schemas.configuration import DefaultsAcceptance
from catalog.schemas.item_input import ItemInput
from catalog.schemas.units import ExpectedVersion, UnitConversionInput


class GroupAssignmentInput(ExpectedVersion):
    group_id: uuid.UUID
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class CategorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheme_id: uuid.UUID
    category_id: uuid.UUID
    is_primary: StrictBool = False


class CategoryAssignmentInput(ExpectedVersion):
    categories: list[CategorySelection] = Field(max_length=128)
    valid_from: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    preview_token: str | None = Field(default=None, min_length=1, max_length=8192)


class CategoryAssignmentPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family_id: uuid.UUID
    expected_version: int
    valid_from: dt.date | None
    membership_count: int
    closing_count: int
    policy_generation: int
    source_version: int
    preview_token: str


class ManufacturerAssignmentInput(ExpectedVersion):
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


class AttributeSelection(TypedValueFields):
    definition_id: uuid.UUID
    value_type: ValueType
    option_id: uuid.UUID | None = None


class AttributeAssignmentInput(ExpectedVersion):
    attributes: list[AttributeSelection] = Field(max_length=128)


class FamilyAttributeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition_id: uuid.UUID
    is_axis: StrictBool = False
    is_required: StrictBool = False
    position: int = Field(strict=True, ge=0, lt=128)
    options: list[uuid.UUID] = Field(default_factory=list, max_length=128)


class FamilyAttributesInput(ExpectedVersion):
    expected_default_item_version: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=2**31 - 1,
        description="Required when replacing default SKU attributes or declaring variant axes.",
    )
    attributes: list[FamilyAttributeInput] = Field(max_length=128)
    default_item_attributes: list[AttributeSelection] = Field(default_factory=list, max_length=128)


class VariantInput(ExpectedVersion):
    item: ItemInput
    attributes: list[AttributeSelection] = Field(max_length=128)


class UnitBindingInput(ExpectedVersion):
    accept_defaults: DefaultsAcceptance | None = None
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    unit_id: uuid.UUID
    role: Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK", "MEASURED"]
    pack_type_id: uuid.UUID | None = None
    conversion_mode: Literal["FIXED", "MEASURED"] = "FIXED"
    numerator: int | None = Field(default=None, strict=True, ge=1, lt=2**63)
    denominator: int | None = Field(default=None, strict=True, ge=1, lt=2**63)
    nominal_ratio: Decimal | None = None
    secondary_unit_id: uuid.UUID | None = None
    quantity_decimal_places: int = Field(strict=True, ge=0, le=4)
    quantity_increment: Decimal
    fractional_entry: StrictBool = False
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))

    @field_validator("numerator", "denominator", mode="before", json_schema_input_type=str | None)
    @classmethod
    def ratio_part(cls, value: Any) -> Any:
        # Retain native integers and the existing command receipt identity.
        return None if value is None else UnitConversionInput.exact_ratio_part(value)

    @field_validator(
        "quantity_increment", "nominal_ratio", mode="before", json_schema_input_type=str | None
    )
    @classmethod
    def exact(cls, value: Any) -> Decimal | None:
        return None if value is None else exact_decimal(value)


class UnitRevisionInput(UnitBindingInput):
    binding_id: uuid.UUID


class BarcodeInput(ExpectedVersion):
    binding_id: uuid.UUID | None = None
    value: str = Field(min_length=1, max_length=128)
    symbology: Literal["GTIN", "CODE128", "QR"] = "CODE128"


class BarcodeGenerateInput(ExpectedVersion):
    binding_id: uuid.UUID | None = None


class BarcodeStateInput(ExpectedVersion):
    barcode_id: uuid.UUID
    is_active: StrictBool


class BarcodeResolveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_value: str = Field(min_length=1, max_length=256)
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class BarcodeResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barcode_id: uuid.UUID
    matched_value: str
    item_id: uuid.UUID
    item_version: int
    sku: str
    name: str
    unit_id: uuid.UUID
    binding_id: uuid.UUID
    unit_revision_id: uuid.UUID
    usage_role: Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK"]
    numerator: int
    denominator: int
    lot_hint: str | None = None
    expiry_yymmdd_hint: str | None = None
    serial_hint: str | None = None

    @field_serializer("numerator", "denominator")
    def ratio_wire(self, value: int) -> str:
        return str(value)


class AuthoringResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family_id: uuid.UUID
    family_version: int
    item_id: uuid.UUID | None = None
    item_version: int | None = None
    changed_ids: list[uuid.UUID]
    policy_generation: int


class AuthoringQuery(ListQuery):
    as_of: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class ProductRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family_id: uuid.UUID
    item_id: uuid.UUID
    family_version: int
    item_version: int
    as_of: dt.date
    missing: list[str]
    product_definition_complete: bool
    activation_available: Literal[True] = True
    policy_generation: int


class AdoptionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class AdoptionCommit(ExpectedVersion):
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    preview_token: str = Field(min_length=1, max_length=4096)


class AdoptionPreview(BaseModel):
    resolution_version: Literal[2] = 2
    purpose: Literal["DRAFT_CONFIGURATION", "ACTIVATION"] = "DRAFT_CONFIGURATION"
    active_adoption_supported: Literal[False] = False
    blocked_reasons: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    expected_version: int
    eligible: bool
    missing: list[str]
    preview_token: str
    current_revision_ids: list[uuid.UUID]
    proposed_revision_ids: list[uuid.UUID]
    policy_generation: int
    source_version: int


class QuantityComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_revision_id: uuid.UUID
    quantity: Decimal
    measured_base_quantity: Decimal | None = None

    @field_validator(
        "quantity", "measured_base_quantity", mode="before", json_schema_input_type=str | None
    )
    @classmethod
    def exact(cls, value: Any) -> Decimal | None:
        return None if value is None else exact_decimal(value)


class QuantityPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    components: list[QuantityComponent] = Field(min_length=1, max_length=32)


class QuantityPreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    base_unit_id: uuid.UUID
    base_quantity: Decimal
    components: list[QuantityComponent]
