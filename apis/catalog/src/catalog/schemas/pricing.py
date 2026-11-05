"""Strict native pricing inputs; no caller-provided cost or physical allocation facts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from billing_platform.exact import exact_decimal
from billing_platform.listing import ListQuery
from pydantic import BaseModel, BeforeValidator, Field, StrictBool, field_validator, model_validator

from catalog.domain.pricing import RateGrid, percentage
from catalog.schemas.configuration import DefaultsAcceptance, StrictInput
from catalog.schemas.customer_pricing import CustomerPricingChain
from catalog.schemas.units import ExpectedVersion

Purpose = Literal["SALE", "PURCHASE", "REFERENCE_RETAIL"]
TaxBasis = Literal["EXCLUSIVE", "INCLUSIVE"]
EstimateKind = Literal["STANDARD_ESTIMATE", "REPLACEMENT_ESTIMATE", "SERVICE_ESTIMATE"]
UnitMode = Literal["EXPLICIT_ONLY", "EXACT_BASE_DERIVATION"]


type ExactDecimal = Annotated[Decimal, BeforeValidator(exact_decimal, json_schema_input_type=str)]


class PricingInput(StrictInput):
    @field_validator("*", mode="after")
    @classmethod
    def printable_strings(cls, value: Any) -> Any:
        if isinstance(value, str) and (not value.strip() or any(ord(c) < 32 for c in value)):
            raise ValueError("text must contain printable characters")
        return value.strip() if isinstance(value, str) else value


class LevelCreate(PricingInput):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    name: str = Field(min_length=1, max_length=100)
    ordinal: int = Field(strict=True, ge=1, le=64)


class LevelPatch(ExpectedVersion):
    name: str = Field(min_length=1, max_length=100)
    is_active: StrictBool


class BootstrapInput(StrictInput):
    pass


class PlanCreate(PricingInput):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    name: str = Field(min_length=1, max_length=100)
    purpose: Purpose
    price_level_id: uuid.UUID | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tax_basis: TaxBasis
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def level_semantics(self) -> Self:
        if (self.purpose == "SALE") != (self.price_level_id is not None):
            raise ValueError("only sale books require a sale level")
        return self


class PlanPatch(ExpectedVersion):
    name: str = Field(min_length=1, max_length=100)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class PublicationInput(PricingInput):
    expected_generation: int = Field(strict=True, ge=1, le=2**63 - 1)
    expected_source_version: int = Field(strict=True, ge=1, le=2**63 - 1)


class DatedInput(PublicationInput):
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    supersedes_id: uuid.UUID | None = None
    expected_previous_version: int | None = Field(default=None, strict=True, ge=1, le=2**31 - 1)

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("effective end precedes start")
        if (self.supersedes_id is None) != (self.expected_previous_version is None):
            raise ValueError("replacement requires both predecessor and expected version")
        return self


class PolicyInput(DatedInput):
    default_level_id: uuid.UUID
    missing_price_policy: Literal["ERROR", "FALLBACK"] = "ERROR"
    fallback_level_id: uuid.UUID | None = None
    purchase_plan_id: uuid.UUID | None = None
    sale_unit_mode: UnitMode = "EXPLICIT_ONLY"
    purchase_unit_mode: UnitMode = "EXPLICIT_ONLY"

    @model_validator(mode="after")
    def fallback_shape(self) -> Self:
        if (self.missing_price_policy == "FALLBACK") != (self.fallback_level_id is not None):
            raise ValueError("fallback policy must name exactly one alternate level")
        if self.default_level_id == self.fallback_level_id:
            raise ValueError("fallback cannot select the default level")
        return self


class ScopeInput(PricingInput):
    item_id: uuid.UUID


class NumericInput(DatedInput):
    accept_defaults: DefaultsAcceptance | None = None
    item_id: uuid.UUID
    unit_revision_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    price_decimal_places: int = Field(strict=True, ge=0, le=4)
    price_increment: ExactDecimal | None = None

    @model_validator(mode="after")
    def grid(self) -> Self:
        RateGrid(self.price_decimal_places, self.price_increment)
        return self


class SeriesInput(PricingInput):
    plan_id: uuid.UUID
    price_scope_id: uuid.UUID
    unit_revision_id: uuid.UUID
    channel_code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")


class TierInput(PricingInput):
    min_quantity: ExactDecimal = Field(ge=0)
    max_quantity: ExactDecimal | None = Field(default=None, gt=0)
    amount: ExactDecimal = Field(ge=0)


class PurchaseTermInput(PricingInput):
    gross_amount: ExactDecimal = Field(gt=0)
    discount_kind: Literal["NONE", "PERCENT", "FIXED_PER_BASIS"]
    discount_value: ExactDecimal = Field(ge=0)


class FormulaInput(PricingInput):
    recipe: Literal[
        "MRP_LESS_PERCENT", "REFERENCE_COST_PLUS_MARKUP", "REFERENCE_COST_TARGET_MARGIN"
    ]
    percentage: ExactDecimal = Field(ge=0)
    estimate_kind: EstimateKind | None = None
    jurisdiction: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_-]{1,19}$")
    rounding_mode: Literal["HALF_UP", "UP", "DOWN"]

    @model_validator(mode="after")
    def source_shape(self) -> Self:
        if self.recipe == "MRP_LESS_PERCENT":
            percentage(self.percentage)
            if self.jurisdiction is None or self.estimate_kind is not None:
                raise ValueError("MRP recipe requires only its declaration jurisdiction")
        else:
            if self.estimate_kind is None or self.jurisdiction is not None:
                raise ValueError("cost recipe requires only its estimate kind")
            if self.recipe == "REFERENCE_COST_TARGET_MARGIN":
                percentage(self.percentage, margin=True)
        return self


class DraftInput(PricingInput):
    series_id: uuid.UUID
    numeric_revision_id: uuid.UUID
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    price_method: Literal["FIXED", "TIERS", "FORMULA"]
    amount: ExactDecimal | None = Field(default=None, ge=0)
    price_basis_quantity: ExactDecimal = Field(gt=0)
    tiers: list[TierInput] = Field(default_factory=list, max_length=64)
    purchase_term: PurchaseTermInput | None = None
    formula: FormulaInput | None = None

    @model_validator(mode="after")
    def method_shape(self) -> Self:
        if (self.price_method == "FIXED") != (self.amount is not None):
            raise ValueError("fixed prices require exactly one amount")
        if (self.price_method == "TIERS") != bool(self.tiers):
            raise ValueError("volume pricing requires only its tier amounts")
        if (self.price_method == "FORMULA") != (self.formula is not None):
            raise ValueError("derived prices require exactly one native recipe")
        if self.purchase_term is not None and self.price_method != "FIXED":
            raise ValueError("gross purchase terms currently require a fixed net reference")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("effective end precedes start")
        return self


class DraftReplace(DraftInput):
    expected_version: int = Field(strict=True, ge=1, le=2**31 - 1)


class PublishInput(PublicationInput):
    expected_version: int = Field(strict=True, ge=1, le=2**31 - 1)
    supersedes_id: uuid.UUID | None = None
    expected_previous_version: int | None = Field(default=None, strict=True, ge=1, le=2**31 - 1)

    @model_validator(mode="after")
    def predecessor_shape(self) -> Self:
        if (self.supersedes_id is None) != (self.expected_previous_version is None):
            raise ValueError("replacement requires both predecessor and expected version")
        return self


class ReferenceInput(DatedInput):
    item_id: uuid.UUID
    unit_revision_id: uuid.UUID
    numeric_revision_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: ExactDecimal = Field(gt=0)
    price_basis_quantity: ExactDecimal = Field(gt=0)
    tax_basis: TaxBasis
    source_reference: str = Field(min_length=1, max_length=500)


class CostInput(ReferenceInput):
    estimate_kind: EstimateKind
    tax_basis: Literal["EXCLUSIVE"] = "EXCLUSIVE"


class MrpInput(ReferenceInput):
    jurisdiction: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,19}$")
    tax_basis: Literal["INCLUSIVE"] = "INCLUSIVE"


class GuardInput(DatedInput):
    item_id: uuid.UUID
    unit_revision_id: uuid.UUID
    numeric_revision_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    rule_kind: Literal["FIXED_MIN", "FIXED_MAX", "MIN_MARGIN", "MIN_MARKUP"]
    amount: ExactDecimal | None = Field(default=None, gt=0)
    percentage: ExactDecimal | None = Field(default=None, ge=0)
    price_basis_quantity: ExactDecimal = Field(gt=0)
    tax_basis: Literal["EXCLUSIVE"] = "EXCLUSIVE"
    estimate_kind: EstimateKind | None = None
    severity: Literal["BLOCK", "REQUIRE_APPROVAL"] = "BLOCK"
    source_reference: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def guard_shape(self) -> Self:
        fixed = self.rule_kind.startswith("FIXED_")
        if (
            fixed != (self.amount is not None)
            or fixed == (self.percentage is not None)
            or fixed == (self.estimate_kind is not None)
        ):
            raise ValueError("guard requires either a fixed amount or an estimate-based percentage")
        if self.rule_kind == "MIN_MARGIN":
            assert self.percentage is not None
            percentage(self.percentage, margin=True)
        return self


class CommercialScopeInput(PricingInput):
    owner_kind: Literal["COMPANY", "GROUP", "FAMILY", "SKU"]
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def owner_shape(self) -> Self:
        if any(
            (self.owner_kind == kind) != (getattr(self, field) is not None)
            for kind, field in (("GROUP", "group_id"), ("FAMILY", "family_id"), ("SKU", "item_id"))
        ):
            raise ValueError("commercial scope requires exactly its typed owner")
        return self


class DiscountInput(DatedInput):
    scope_id: uuid.UUID
    max_discount_pct: ExactDecimal = Field(ge=0, le=100)


class CommercialInput(DatedInput):
    item_id: uuid.UUID
    free_sale_allowed: StrictBool


class PricingQuery(ListQuery):
    item_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    scope_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    draft_id: uuid.UUID | None = None
    price_level_id: uuid.UUID | None = None
    channel_code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    purpose: Purpose | None = None
    as_of: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class ResolveInput(PricingInput):
    item_id: uuid.UUID
    lot_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    quantity: ExactDecimal = Field(gt=0)
    purpose: Purpose = "SALE"
    party_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    price_level_id: uuid.UUID | None = None
    channel_code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    override_reason: str | None = Field(default=None, min_length=1, max_length=250)
    jurisdiction: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_-]{1,19}$")


class CommandOutput(StrictInput):
    id: uuid.UUID
    row_version: int
    policy_generation: int
    source_version: int


class PricingIssue(StrictInput):
    code: str
    as_of: dt.date
    message: str


type TransactionRequirement = Literal["TAX_CONTEXT", "MEASURED_QUANTITY"]


class DraftPreview(CommandOutput):
    valid: bool = True
    source_ids: list[uuid.UUID]
    amount: Decimal | None
    currency: str
    price_basis_quantity: Decimal
    tax_basis: str
    issues: list[PricingIssue] = Field(default_factory=list)
    guard_ids: list[uuid.UUID] = Field(default_factory=list)
    approval_guard_ids: list[uuid.UUID] = Field(default_factory=list)
    transaction_requirements: list[TransactionRequirement] = Field(default_factory=list)
    final_guard_validation_required: Literal[True] = True
    coverage_valid_to: dt.date | None = None
    publishable: bool = True
    publication_issues: list[PricingIssue] = Field(default_factory=list)
    supersedes_id: uuid.UUID | None = None
    expected_previous_version: int | None = None


class ExactRatio(BaseModel):
    numerator: str
    denominator: str


class PriceResolution(StrictInput):
    status: Literal["RESOLVED", "MISSING", "NEEDS_TAX_CONTEXT"]
    item_id: uuid.UUID
    lot_id: uuid.UUID | None = None
    as_of: dt.date
    purpose: Purpose
    currency: str
    requested_unit_revision_id: uuid.UUID
    pricing_unit_revision_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    price_level_id: uuid.UUID | None = None
    buyer_party_id: uuid.UUID | None = None
    buyer_price_level_id: uuid.UUID | None = None
    buyer_pricing_chain: tuple[CustomerPricingChain, ...] = ()
    requested_channel_code: str | None = None
    selected_channel_code: str | None = None
    series_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    tier_id: uuid.UUID | None = None
    numeric_revision_id: uuid.UUID | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    quantity: Decimal
    exact_consideration: ExactRatio | None = None
    fallback_used: bool = False
    unit_derivation_used: bool = False
    source_ids: list[uuid.UUID] = Field(default_factory=list)
    minimum_rate: ExactRatio | None = None
    maximum_rate: ExactRatio | None = None
    max_discount_pct: Decimal | None = None
    approval_guard_ids: list[uuid.UUID] = Field(default_factory=list)
    guard_ids: list[uuid.UUID] = Field(default_factory=list)
    final_guard_validation_required: bool = True
    purchase_term: PurchaseTermInput | None = None
    policy_generation: int
    source_version: int
