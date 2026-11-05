"""Bounded wizard context and private, incomplete saved work."""

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from catalog.schemas.classification import MasterInput
from catalog.schemas.configuration import AuthoringDefaults, StrictInput
from catalog.schemas.field_metadata import FieldSet
from catalog.schemas.item_input import ItemInput
from catalog.schemas.pricing import EstimateKind, ExactDecimal
from catalog.schemas.product_authoring import AttributeSelection, FamilyAttributeInput
from catalog.schemas.product_initial import InitialProductSetup
from catalog.schemas.product_mode import ProductModeDetail
from catalog.schemas.products import FamilyDetail, ItemDetail
from catalog.schemas.simple_product_creation import (
    SimpleBatchOptions,
    SimpleBatchInput,
    SimpleRequiredCategoryScheme,
    SimpleSalePriceOption,
    SimpleSerialInput,
    SimpleSerialOptions,
)


class AdvancedTypeOption(StrictInput):
    id: uuid.UUID
    kind: Literal["GOODS", "SERVICE"]
    unit_dimensions: list[str] = Field(max_length=32)
    inventory_modes: list[str] = Field(max_length=16)
    tracking_modes: list[str] = Field(max_length=16)
    allow_variants: bool
    require_brand: bool
    require_manufacturer: bool
    require_expiry: bool


class AdvancedCreationOptions(StrictInput):
    company_id: uuid.UUID
    kind: Literal["GOODS", "SERVICE"]
    today: dt.date
    currency: str
    mode: ProductModeDetail
    defaults: AuthoringDefaults
    default_group_id: uuid.UUID | None
    selected_type: AdvancedTypeOption | None
    inventory_enabled: bool
    batch: SimpleBatchOptions = Field(default_factory=SimpleBatchOptions)
    serial: SimpleSerialOptions = Field(default_factory=SimpleSerialOptions)
    gst_enabled: bool
    price_levels_accessible: bool
    family_fields: FieldSet
    sku_fields: FieldSet
    sale_price_levels: list[SimpleSalePriceOption] = Field(default_factory=list, max_length=64)
    required_category_schemes: list[SimpleRequiredCategoryScheme] = Field(
        default_factory=list, max_length=128
    )
    max_skus_per_draft: Literal[64] = 64


def _bounded(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("draft nesting exceeds eight levels")
    if isinstance(value, float):
        raise ValueError("enter decimal amounts and quantities as strings")
    if isinstance(value, dict):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 100 for key in value):
            raise ValueError("draft section has too many or oversized keys")
        for entry in value.values():
            _bounded(entry, depth + 1)
    elif isinstance(value, list):
        if len(value) > 256:
            raise ValueError("draft section has too many entries")
        for entry in value:
            _bounded(entry, depth + 1)
    elif value is not None and not isinstance(value, str | int | bool):
        raise ValueError("draft contains an unsupported value")


class AdvancedDraftContent(StrictInput):
    """Transport state only; submission uses a separate strict native command."""

    profile: dict[str, Any] = Field(default_factory=dict, max_length=128)
    skus: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    business: dict[str, Any] = Field(default_factory=dict, max_length=128)
    opening: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="after")
    def bounded_json(self) -> Self:
        data = self.model_dump()
        _bounded(data)
        if (
            len(json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
            > 65536
        ):
            raise ValueError("save up to 64 KiB in one product draft")
        return self


class AdvancedDraftSave(StrictInput):
    mode_version: int = Field(strict=True, ge=0, lt=2**31)
    policy_generation: int = Field(strict=True, ge=1, lt=2**63)
    source_version: int = Field(strict=True, ge=0, lt=2**63)
    family_field_version: int = Field(strict=True, ge=0, lt=2**63)
    sku_field_version: int = Field(strict=True, ge=0, lt=2**63)
    step: int = Field(strict=True, ge=1, le=4)
    content: AdvancedDraftContent


class AdvancedDraftRevision(AdvancedDraftSave):
    expected_version: int = Field(strict=True, ge=1, lt=2**31)


class AdvancedDraftListItem(StrictInput):
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    step: int
    updated_at: dt.datetime
    needs_review: bool


class AdvancedDraftDetail(AdvancedDraftListItem):
    created_at: dt.datetime
    mode_version: int
    policy_generation: int
    source_version: int
    family_field_version: int
    sku_field_version: int
    content: AdvancedDraftContent


class AdvancedProfileInput(MasterInput):
    kind: Literal["GOODS", "SERVICE"]
    product_type_revision_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    model_code: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="after")
    def series_brand(self) -> Self:
        if self.series_id is not None and self.brand_id is None:
            raise ValueError("series requires its brand")
        return self


class AdvancedSkuInput(StrictInput):
    item: ItemInput
    attributes: list[AttributeSelection] = Field(default_factory=list, max_length=128)


class AdvancedDefinitionCreate(StrictInput):
    """Exact, bounded native definition command; SKU zero is the default slot."""

    mode_version: int = Field(strict=True, ge=1, lt=2**31)
    policy_generation: int = Field(strict=True, ge=1, lt=2**63)
    source_version: int = Field(strict=True, ge=0, lt=2**63)
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    group_id: uuid.UUID | None = None
    profile: AdvancedProfileInput
    attributes: list[FamilyAttributeInput] = Field(default_factory=list, max_length=128)
    skus: list[AdvancedSkuInput] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def bounded_definition(self) -> Self:
        if len({sku.item.sku for sku in self.skus}) != len(self.skus):
            raise ValueError("SKU codes must be distinct")
        axes = [entry for entry in self.attributes if entry.is_axis]
        if not axes and len(self.skus) != 1:
            raise ValueError("multiple SKUs require variant axes")
        payload = self.model_dump(mode="json")
        _bounded(payload)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise ValueError("submit up to 64 KiB of product definitions")
        return self


class AdvancedSkuProgress(StrictInput):
    item_id: uuid.UUID
    setup_done: bool = False
    price_draft_ids: list[uuid.UUID] = Field(default_factory=list, max_length=65)
    published_price_ids: list[uuid.UUID] = Field(default_factory=list, max_length=65)
    purchase_reference_id: uuid.UUID | None = None
    mrp_id: uuid.UUID | None = None
    activated: bool = False
    opening_state: Literal["NOT_REQUESTED", "SKIPPED", "IN_PROGRESS", "POSTED"] = "NOT_REQUESTED"
    opening_step: str | None = None
    opening_control_id: uuid.UUID | None = None
    opening_voucher_id: uuid.UUID | None = None
    opening_operation_id: uuid.UUID | None = None


class AdvancedDefinitionStatus(StrictInput):
    id: uuid.UUID
    company_id: uuid.UUID
    status: Literal["DEFINED", "SETUP", "ACTIVATING", "OPENING", "COMPLETE"]
    step: str
    row_version: int
    family_id: uuid.UUID
    sku_ids: list[uuid.UUID] = Field(max_length=64)
    sku_progress: list[AdvancedSkuProgress] = Field(default_factory=list, max_length=64)


class AdvancedDefinitionResult(StrictInput):
    creation: AdvancedDefinitionStatus
    family: FamilyDetail
    skus: list[ItemDetail] = Field(max_length=64)


class AdvancedPurchaseReference(StrictInput):
    amount: ExactDecimal = Field(gt=0)
    price_basis_quantity: ExactDecimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    price_decimal_places: int = Field(strict=True, ge=0, le=4)
    estimate_kind: EstimateKind
    source_reference: str = Field(min_length=1, max_length=500)


class AdvancedMrpReference(StrictInput):
    amount: ExactDecimal = Field(gt=0)
    price_basis_quantity: ExactDecimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    price_decimal_places: int = Field(strict=True, ge=0, le=4)
    jurisdiction: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,19}$")
    source_reference: str = Field(min_length=1, max_length=500)


class AdvancedSkuSetup(StrictInput):
    expected_creation_version: int = Field(strict=True, ge=1, lt=2**31)
    expected_family_version: int = Field(strict=True, ge=1, lt=2**31)
    expected_item_version: int = Field(strict=True, ge=1, lt=2**31)
    setup: InitialProductSetup
    purchase_reference: AdvancedPurchaseReference | None = None
    mrp: AdvancedMrpReference | None = None

    @model_validator(mode="after")
    def definitions_already_saved(self) -> Self:
        if self.setup.attributes is not None:
            raise ValueError("SKU attributes were saved with the Product Profile")
        if (self.purchase_reference is not None or self.mrp is not None) and (
            self.setup.expected_generation is None or self.setup.expected_source_version is None
        ):
            raise ValueError("purchase reference and MRP require reviewed configuration versions")
        if len(json.dumps(self.model_dump(mode="json"), allow_nan=False).encode()) > 65536:
            raise ValueError("submit up to 64 KiB of SKU setup")
        return self


class AdvancedSkuPublish(StrictInput):
    expected_creation_version: int = Field(strict=True, ge=1, lt=2**31)


class AdvancedSkuActivate(StrictInput):
    expected_creation_version: int = Field(strict=True, ge=1, lt=2**31)
    expected_family_version: int = Field(strict=True, ge=1, lt=2**31)
    expected_item_version: int = Field(strict=True, ge=1, lt=2**31)
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    expected_generation: int = Field(strict=True, ge=1, lt=2**63)
    expected_source_version: int = Field(strict=True, ge=1, lt=2**63)


class AdvancedReadinessRequest(StrictInput):
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class AdvancedReadinessBlocker(StrictInput):
    code: str
    step: Literal["profile", "skus", "business"]
    path: str


class AdvancedSkuReadiness(StrictInput):
    item_id: uuid.UUID
    eligible: bool
    blockers: list[AdvancedReadinessBlocker] = Field(max_length=256)
    item_version: int
    family_version: int
    policy_generation: int
    source_version: int | None


class AdvancedOpeningInput(StrictInput):
    decision: Literal["SKIP", "OPEN"]
    opening_date: dt.date | None = None
    warehouse_id: uuid.UUID | None = None
    opening_quantity: ExactDecimal = Field(default=Decimal("0"), ge=0)
    purchase_price: ExactDecimal | None = Field(default=None, ge=0)
    batches: list[SimpleBatchInput] = Field(default_factory=list, max_length=64)
    serials: list[SimpleSerialInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.decision == "SKIP":
            if (
                self.opening_date is not None
                or self.warehouse_id is not None
                or self.opening_quantity
                or self.purchase_price is not None
                or self.batches
                or self.serials
            ):
                raise ValueError("skip opening without stock details")
            return self
        if self.opening_date is None:
            raise ValueError("select the books-begin date for opening stock")
        if self.batches and (
            self.opening_quantity or self.purchase_price is not None or self.serials
        ):
            raise ValueError("enter opening quantity and identifiers on batch rows")
        if not self.batches and (not self.opening_quantity or self.purchase_price is None):
            raise ValueError("opening stock requires quantity and purchase cost")
        if self.batches and any(not row.opening_quantity for row in self.batches):
            raise ValueError("opening batches require a positive quantity")
        count = len(self.serials) + sum(len(row.serials) for row in self.batches)
        if count > 200:
            raise ValueError("capture up to 200 physical serial units")
        if self.serials and Decimal(count) != self.opening_quantity:
            raise ValueError("serial count must equal opening quantity")
        for row in self.batches:
            if row.serials and Decimal(len(row.serials)) != row.opening_quantity:
                raise ValueError("batch serial count must equal batch opening quantity")
        if len(json.dumps(self.model_dump(mode="json"), allow_nan=False).encode()) > 65536:
            raise ValueError("submit up to 64 KiB of one SKU opening")
        return self


class AdvancedOpeningSubmit(StrictInput):
    expected_creation_version: int = Field(strict=True, ge=1, lt=2**31)
    opening: AdvancedOpeningInput


class AdvancedOpeningCheck(StrictInput):
    item_id: uuid.UUID
    opening_date: dt.date | None
    warehouse_id: uuid.UUID | None
    total_quantity: ExactDecimal
    batch_count: int
    serial_count: int
