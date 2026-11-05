"""Typed aggregate authoring and bounded configuration browse contracts."""

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
    field_validator,
    model_validator,
)

from catalog.domain.configuration import NumericDefault, OptionSetting
from catalog.domain.units import QuantityRule
from catalog.schemas.options import OptionItem
from catalog.schemas.units import Dimension, ExpectedVersion

Requirement = Literal["INHERIT", "DISABLED", "OPTIONAL", "REQUIRED"]
PricingDimensionMode = Literal["INHERIT", "DISABLED", "ENABLED"]
ProfileMode = Literal["INHERIT", "CLEAR", "VALUE"]
ScopeKind = Literal["COMPANY", "TYPE", "GROUP", "FAMILY", "SKU"]


class ConfigurationOptionItem(OptionItem):
    """A protected native parent for opening the selected record's existing page."""

    parent_id: uuid.UUID | None = None


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def real_identifiers(cls, value: Any) -> Any:
        if isinstance(value, uuid.UUID) and value.int == 0:
            raise ValueError("a real Catalog identifier is required")
        return value


class ScopeCreate(StrictInput):
    scope_kind: Literal["COMPANY"] = "COMPANY"


class EntryOptions(StrictInput):
    variants_mode: Requirement = "INHERIT"
    variants_default: StrictBool | None = None
    barcode_mode: Requirement = "INHERIT"
    barcode_default: StrictBool | None = None
    brand_mode: Requirement = "INHERIT"
    brand_default: StrictBool | None = None
    model_mode: Requirement = "INHERIT"
    model_default: StrictBool | None = None
    category_mode: Requirement = "INHERIT"
    category_default: StrictBool | None = None
    manufacturer_mode: Requirement = "INHERIT"
    manufacturer_default: StrictBool | None = None
    alternate_units_mode: Requirement = "INHERIT"
    alternate_units_default: StrictBool | None = None
    compound_units_mode: Requirement = "INHERIT"
    compound_units_default: StrictBool | None = None
    measured_units_mode: Requirement = "INHERIT"
    measured_units_default: StrictBool | None = None

    @model_validator(mode="after")
    def consistent_choices(self) -> Self:
        OptionSetting(self.variants_mode, self.variants_default)
        OptionSetting(self.barcode_mode, self.barcode_default)
        OptionSetting(self.brand_mode, self.brand_default)
        OptionSetting(self.model_mode, self.model_default)
        OptionSetting(self.category_mode, self.category_default)
        OptionSetting(self.manufacturer_mode, self.manufacturer_default)
        OptionSetting(self.alternate_units_mode, self.alternate_units_default)
        OptionSetting(self.compound_units_mode, self.compound_units_default)
        OptionSetting(self.measured_units_mode, self.measured_units_default)
        return self


class NumericInput(StrictInput):
    dimension: Dimension
    quantity_decimal_places: int | None = Field(default=None, strict=True, ge=0, le=4)
    quantity_increment: Decimal | None = None
    price_decimal_places: int | None = Field(default=None, strict=True, ge=0, le=4)
    price_increment: Decimal | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    price_basis_quantity: Decimal | None = None

    @field_validator(
        "quantity_increment",
        "price_increment",
        "price_basis_quantity",
        mode="before",
        json_schema_input_type=str | None,
    )
    @classmethod
    def exact_entries(cls, value: Any) -> Decimal | None:
        return None if value is None else exact_decimal(value)

    @model_validator(mode="after")
    def exact_defaults(self) -> Self:
        if (self.quantity_decimal_places is None) != (self.quantity_increment is None):
            raise ValueError("quantity defaults require both precision and increment")
        quantity = None
        if self.quantity_decimal_places is not None and self.quantity_increment is not None:
            quantity = QuantityRule(self.quantity_decimal_places, self.quantity_increment)
        NumericDefault(
            self.dimension,
            quantity,
            self.price_decimal_places,
            self.price_increment,
            self.currency,
            self.price_basis_quantity,
        )
        return self


class ProfileDefaults(StrictInput):
    goods_type_revision_mode: ProfileMode = "INHERIT"
    goods_type_revision_id: uuid.UUID | None = None
    service_type_revision_mode: ProfileMode = "INHERIT"
    service_type_revision_id: uuid.UUID | None = None
    inventory_template_revision_mode: ProfileMode = "INHERIT"
    inventory_template_revision_id: uuid.UUID | None = None
    warranty_revision_mode: ProfileMode = "INHERIT"
    warranty_revision_id: uuid.UUID | None = None
    return_policy_revision_mode: ProfileMode = "INHERIT"
    return_policy_revision_id: uuid.UUID | None = None
    handling_revision_mode: ProfileMode = "INHERIT"
    handling_revision_id: uuid.UUID | None = None
    identifier_profile_mode: ProfileMode = "INHERIT"
    identifier_profile_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def referenced_defaults(self) -> Self:
        if (self.goods_type_revision_mode == "VALUE") != (self.goods_type_revision_id is not None):
            raise ValueError("goods_type_revision needs exactly its selected reference")
        if (self.service_type_revision_mode == "VALUE") != (
            self.service_type_revision_id is not None
        ):
            raise ValueError("service_type_revision needs exactly its selected reference")
        if (self.inventory_template_revision_mode == "VALUE") != (
            self.inventory_template_revision_id is not None
        ):
            raise ValueError("inventory_template_revision needs exactly its selected reference")
        if (self.warranty_revision_mode == "VALUE") != (self.warranty_revision_id is not None):
            raise ValueError("warranty_revision needs exactly its selected reference")
        if (self.return_policy_revision_mode == "VALUE") != (
            self.return_policy_revision_id is not None
        ):
            raise ValueError("return_policy_revision needs exactly its selected reference")
        if (self.handling_revision_mode == "VALUE") != (self.handling_revision_id is not None):
            raise ValueError("handling_revision needs exactly its selected reference")
        if (self.identifier_profile_mode == "VALUE") != (self.identifier_profile_id is not None):
            raise ValueError("identifier_profile needs exactly its selected reference")
        return self


class PricingRequirements(StrictInput):
    multiple_price_levels_mode: PricingDimensionMode = "INHERIT"
    purchase_reference_mode: Requirement = "INHERIT"
    sale_price_mode: Requirement = "INHERIT"
    mrp_mode: Requirement = "INHERIT"
    sale_level_count: int | None = Field(default=None, strict=True, ge=1, le=64)
    unit_prices_mode: PricingDimensionMode = "INHERIT"
    quantity_tiers_mode: PricingDimensionMode = "INHERIT"
    channel_prices_mode: PricingDimensionMode = "INHERIT"
    additional_currencies_mode: PricingDimensionMode = "INHERIT"
    formula_prices_mode: PricingDimensionMode = "INHERIT"


class CompanyDraftInput(StrictInput):
    """The owner is bound from the authorised company, never selected by the caller."""

    effective_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    change_reason: str = Field(min_length=1, max_length=250)
    options: EntryOptions = Field(default_factory=EntryOptions)
    numeric_defaults: list[NumericInput] = Field(default_factory=list, max_length=7)
    profiles: ProfileDefaults = Field(default_factory=ProfileDefaults)
    pricing: PricingRequirements = Field(default_factory=PricingRequirements)

    @field_validator("change_reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("change reason must contain printable text")
        return value.strip()

    @field_validator("numeric_defaults")
    @classmethod
    def unique_dimensions(cls, value: list[NumericInput]) -> list[NumericInput]:
        if len({row.dimension for row in value}) != len(value):
            raise ValueError("numeric default dimensions must be unique")
        return value


class DraftInput(CompanyDraftInput):
    """Compatibility input for a verified company scope ID."""

    scope_id: uuid.UUID


class EntryOptionsPatch(EntryOptions):
    @model_validator(mode="after")
    def consistent_choices(self) -> Self:
        # Validate the complete pair after merging with the existing draft.
        return self


class ProfileDefaultsPatch(ProfileDefaults):
    @model_validator(mode="after")
    def referenced_defaults(self) -> Self:
        # An identifier-only or mode-only patch is validated against current values.
        return self


class DraftPatch(ExpectedVersion):
    effective_from: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    change_reason: str | None = Field(default=None, min_length=1, max_length=250)
    options: EntryOptionsPatch | None = None
    numeric_defaults: list[NumericInput] | None = Field(default=None, max_length=7)
    profiles: ProfileDefaultsPatch | None = None
    pricing: PricingRequirements | None = None

    @model_validator(mode="after")
    def no_null_changes(self) -> Self:
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("draft values cannot be null; use explicit inheritance or clear modes")
        if self.change_reason is not None:
            self.change_reason = DraftInput.meaningful_reason(self.change_reason)
        if self.numeric_defaults is not None:
            DraftInput.unique_dimensions(self.numeric_defaults)
        return self


class PublishInput(ExpectedVersion):
    expected_generation: int = Field(strict=True, ge=1, le=2**63 - 1)
    expected_source_version: int = Field(strict=True, ge=1, le=2**63 - 1)


class ScopeQuery(ListQuery):
    scope_kind: Literal["COMPANY"] | None = None


ConfigurationOptionSource = Literal[
    "items",
    "product-type-revisions",
    "attribute-set-revisions",
    "inventory-template-revisions",
    "warranty-revisions",
    "return-policy-revisions",
    "handling-revisions",
    "identifier-profiles",
    "currencies",
]


class ConfigurationOptionQuery(ListQuery):
    kind: Literal["GOODS", "SERVICE"] | None = None
    value: str | None = Field(default=None, min_length=1, max_length=36)


class DraftQuery(ListQuery):
    status: Literal["DRAFT", "PUBLISHED"] | None = None


class RevisionQuery(ListQuery):
    effective_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class DefaultsAcceptance(StrictInput):
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    expected_generation: int = Field(strict=True, ge=1, le=2**63 - 1)
    expected_source_version: int = Field(strict=True, ge=1, le=2**63 - 1)
    group_id: uuid.UUID | None = None


class EffectiveQuery(StrictInput):
    product_type_revision_id: uuid.UUID | None = None
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    kind: Literal["GOODS", "SERVICE"]
    product_type_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None


class ScopeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    scope_kind: ScopeKind | None = None
    owner_id: uuid.UUID | None = None
    product_type_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    row_version: int | None = None
    latest_revision: int | None = None


class ScopeDetail(ScopeListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    policy_generation: int


class ChildDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    draft_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None


class EntryOptionsDetail(ChildDetail):
    variants_mode: Requirement | None = None
    variants_default: bool | None = None
    barcode_mode: Requirement | None = None
    barcode_default: bool | None = None
    brand_mode: Requirement | None = None
    brand_default: bool | None = None
    model_mode: Requirement | None = None
    model_default: bool | None = None
    category_mode: Requirement | None = None
    category_default: bool | None = None
    manufacturer_mode: Requirement | None = None
    manufacturer_default: bool | None = None
    alternate_units_mode: Requirement | None = None
    alternate_units_default: bool | None = None
    compound_units_mode: Requirement | None = None
    compound_units_default: bool | None = None
    measured_units_mode: Requirement | None = None
    measured_units_default: bool | None = None


class NumericDefaultDetail(ChildDetail):
    dimension: Dimension | None = None
    quantity_decimal_places: int | None = None
    quantity_increment: Decimal | None = None
    price_decimal_places: int | None = None
    price_increment: Decimal | None = None
    currency: str | None = None
    price_basis_quantity: Decimal | None = None


class ProfileDefaultsDetail(ChildDetail):
    goods_type_revision_mode: ProfileMode | None = None
    goods_type_revision_id: uuid.UUID | None = None
    service_type_revision_mode: ProfileMode | None = None
    service_type_revision_id: uuid.UUID | None = None
    inventory_template_revision_mode: ProfileMode | None = None
    inventory_template_revision_id: uuid.UUID | None = None
    warranty_revision_mode: ProfileMode | None = None
    warranty_revision_id: uuid.UUID | None = None
    return_policy_revision_mode: ProfileMode | None = None
    return_policy_revision_id: uuid.UUID | None = None
    handling_revision_mode: ProfileMode | None = None
    handling_revision_id: uuid.UUID | None = None
    identifier_profile_mode: ProfileMode | None = None
    identifier_profile_id: uuid.UUID | None = None


class PricingRequirementsDetail(ChildDetail):
    multiple_price_levels_mode: PricingDimensionMode | None = None
    purchase_reference_mode: Requirement | None = None
    sale_price_mode: Requirement | None = None
    mrp_mode: Requirement | None = None
    sale_level_count: int | None = None
    unit_prices_mode: PricingDimensionMode | None = None
    quantity_tiers_mode: PricingDimensionMode | None = None
    channel_prices_mode: PricingDimensionMode | None = None
    additional_currencies_mode: PricingDimensionMode | None = None
    formula_prices_mode: PricingDimensionMode | None = None


class DraftListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    scope_id: uuid.UUID | None = None
    row_version: int | None = None
    status: Literal["DRAFT", "PUBLISHED"] | None = None
    effective_from: dt.date | None = None


class DraftDetail(DraftListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    change_reason: str | None = None
    options: EntryOptionsDetail
    numeric_defaults: list[NumericDefaultDetail]
    profiles: ProfileDefaultsDetail
    pricing: PricingRequirementsDetail
    policy_generation: int


class RevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    scope_id: uuid.UUID | None = None
    revision: int | None = None
    effective_from: dt.date | None = None
    published_at: dt.datetime | None = None


class RevisionDetail(RevisionListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    source_draft_id: uuid.UUID | None = None
    change_reason: str | None = None
    options: EntryOptionsDetail
    numeric_defaults: list[NumericDefaultDetail]
    profiles: ProfileDefaultsDetail
    pricing: PricingRequirementsDetail
    policy_generation: int


class ConfigurationSource(StrictInput):
    scope_id: uuid.UUID
    scope_kind: ScopeKind
    revision_id: uuid.UUID
    revision: int
    effective_from: dt.date


class ConfigurationOrigin(StrictInput):
    kind: Literal["NATIVE", "TYPE", "REVISION", "DRAFT", "UNIT"]
    scope_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    type_revision_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None


class ConfigurationSetting(StrictInput):
    field: str
    origins: list[ConfigurationOrigin] = Field(max_length=36)
    applicable: bool = True
    overrideable: bool = True
    reason: Literal["goods_only", "service_only", "hard_requirement", "hard_prohibition"] | None = (
        None
    )


class EffectiveConfiguration(StrictInput):
    company_id: uuid.UUID
    as_of: dt.date
    kind: Literal["GOODS", "SERVICE"]
    policy_generation: int
    source_version: int
    sources: list[ConfigurationSource]
    options: EntryOptions
    numeric_defaults: list[NumericInput]
    profiles: ProfileDefaults
    pricing: PricingRequirements
    settings: list[ConfigurationSetting] = Field(default_factory=list, max_length=100)
    activation_supported: Literal[True] = True
    activation_available: Literal[True] = Field(
        default=True,
        deprecated=True,
        description="Service support only; use activation preview for SKU eligibility.",
    )
    pending_milestones: tuple[str, ...] = ()


class ConfigurationComparison(StrictInput):
    kind: Literal["GOODS", "SERVICE"]
    before: EffectiveConfiguration | None
    before_conflicts: list[str] = Field(default_factory=list, max_length=1)
    after: EffectiveConfiguration
    changed_fields: list[str] = Field(max_length=128)


class ConfigurationPreview(StrictInput):
    draft_id: uuid.UUID
    draft_version: int
    policy_generation: int
    source_version: int
    effective_from: dt.date
    purpose: Literal["FUTURE_PRODUCT_DEFAULTS"] = "FUTURE_PRODUCT_DEFAULTS"
    existing_product_adoption: Literal["unchanged"] = "unchanged"
    billing_enforcement: Literal["unavailable"] = "unavailable"
    validated: bool
    comparisons: list[ConfigurationComparison] = Field(default_factory=list, max_length=2)


class AuthoringDefaultsQuery(EffectiveQuery):
    include_price: bool = True
    unit_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class QuantitySuggestion(StrictInput):
    unit_id: uuid.UUID
    quantity_decimal_places: int
    quantity_increment: Decimal
    fractional_entry: bool


class PriceSuggestion(StrictInput):
    currency: str
    price_decimal_places: int
    price_increment: Decimal | None
    price_basis_quantity: Decimal


class AuthoringDefaults(StrictInput):
    product_type_revision_id: uuid.UUID | None
    quantity: QuantitySuggestion | None
    price: PriceSuggestion | None
    configuration: EffectiveConfiguration
    acceptance: DefaultsAcceptance
    missing: list[str]
    adjustments: list[str]
