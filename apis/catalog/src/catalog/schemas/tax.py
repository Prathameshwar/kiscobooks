"""Native GST definition inputs; no invoice, registration or place-of-supply guesses."""

import datetime as dt
import re
import uuid
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from billing_platform.listing import ListQuery
from pydantic import Field, StrictBool, field_validator, model_validator

from catalog.domain.tax import GST_CEILINGS
from catalog.schemas.pricing import CommercialScopeInput, DatedInput, ExactDecimal, PricingInput
from catalog.schemas.units import ExpectedVersion

Treatment = Literal["TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"]
Applicability = Literal["INTRA_STATE", "INTRA_UT", "INTER_STATE"]
Bundle = Literal["CLASSIFICATION", "TREATMENT", "RULE"]


class Evidence(PricingInput):
    source_reference: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=1000)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("source_url")
    @classmethod
    def official_source(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith((".gov.in", ".nic.in"))
            or url.username
            or url.password
            or url.port not in {None, 443}
        ):
            raise ValueError("source must identify an official Indian government HTTPS document")
        return value


# Chapter 99 of the GST tariff is the services annexure: those codes are SAC, never goods HSN.
HSN = r"(?!99)[0-9]{4}(?:[0-9]{2}){0,2}"


class ClassificationInput(DatedInput, Evidence):
    jurisdiction: Literal["IN"] = "IN"
    code_system: Literal["HSN", "SAC"]
    code: str
    item_kind: Literal["GOODS", "SERVICE"]
    description: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def classified_kind(self) -> Self:
        pattern = HSN if self.code_system == "HSN" else r"99[0-9]{4}"
        if not re.fullmatch(pattern, self.code) or self.item_kind != (
            "GOODS" if self.code_system == "HSN" else "SERVICE"
        ):
            raise ValueError(
                "HSN goods require 4/6/8 digits outside chapter 99; "
                "SAC services require six digits starting 99"
            )
        return self


class CategoryInput(PricingInput):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    name: str = Field(min_length=1, max_length=100)


class ClassificationMatch(PricingInput):
    code_system: Literal["HSN", "SAC"]
    code: str
    match_kind: Literal["EXACT", "PREFIX"] = "EXACT"

    @model_validator(mode="after")
    def supported_code(self) -> Self:
        pattern = (
            HSN
            if self.code_system == "HSN"
            else (r"99[0-9]{2}(?:[0-9]{2})?" if self.match_kind == "PREFIX" else r"99[0-9]{4}")
        )
        if not re.fullmatch(pattern, self.code):
            raise ValueError("applicability requires a supported HSN/SAC code or prefix")
        return self


class ApplicabilityInput(ClassificationMatch):
    rule_id: uuid.UUID


class RuleInput(CategoryInput, Evidence):
    tax_system: Literal["gst_in"] = "gst_in"
    jurisdiction: Literal["IN"] = "IN"
    item_kind: Literal["GOODS", "SERVICE"]
    treatment: Treatment
    tax_category_id: uuid.UUID
    classification_scope: Literal["SPECIFIC", "ANY"] = "SPECIFIC"
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    classifications: list[ClassificationMatch] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def applicability_shape(self) -> Self:
        if self.classification_scope == "ANY" and self.classifications:
            raise ValueError("generic templates cannot restrict individual classifications")
        return self


class MasterPatch(ExpectedVersion):
    name: str = Field(min_length=1, max_length=100)
    is_active: StrictBool


class RulePatch(MasterPatch):
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class SeriesInput(PricingInput):
    rule_id: uuid.UUID
    applicability: Applicability


class ComponentInput(PricingInput):
    component_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,29}$")
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]
    kind: Literal["PERCENT", "FIXED_PER_UNIT"]
    percentage: ExactDecimal | None = Field(default=None, ge=0)
    amount: ExactDecimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    unit_id: uuid.UUID | None = None
    basis_quantity: ExactDecimal | None = Field(default=None, gt=0)
    rounding_mode: Literal["HALF_UP", "UP", "DOWN"]
    position: int = Field(strict=True, ge=0, le=15)

    @model_validator(mode="after")
    def shape(self) -> Self:
        fixed = (self.amount, self.currency, self.unit_id, self.basis_quantity)
        if self.kind == "PERCENT":
            valid = (
                self.percentage is not None
                and (self.component == "CESS" or self.percentage <= GST_CEILINGS[self.component])
                and all(value is None for value in fixed)
            )
        else:
            valid = (
                self.component == "CESS"
                and self.percentage is None
                and all(value is not None for value in fixed)
            )
        if not valid:
            raise ValueError("component requires percentage or a complete fixed cess unit basis")
        return self


class RateInput(DatedInput, Evidence):
    series_id: uuid.UUID
    components: list[ComponentInput] = Field(min_length=1, max_length=16)


class ScopeInput(CommercialScopeInput):
    pass


class BindingInput(DatedInput):
    scope_id: uuid.UUID
    jurisdiction: Literal["IN"] = "IN"
    direction: Literal["SALE", "PURCHASE"]
    bundle: Bundle
    mode: Literal["INHERIT", "OVERRIDE", "REQUIRE_EXPLICIT"]
    classification_id: uuid.UUID | None = None
    treatment: Treatment | None = None
    exemption_reason: str | None = Field(default=None, min_length=1, max_length=500)
    tax_category_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    # NULL applies to every kind the scope admits; a kind keys a company/BOTH-group default.
    item_kind: Literal["GOODS", "SERVICE"] | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        fields = {
            key
            for key in (
                "classification_id",
                "treatment",
                "exemption_reason",
                "tax_category_id",
                "rule_id",
            )
            if getattr(self, key) is not None
        }
        expected: set[str] = set()
        if self.mode == "OVERRIDE":
            expected = (
                {"classification_id"}
                if self.bundle == "CLASSIFICATION"
                else {"rule_id"}
                if self.bundle == "RULE"
                else {"treatment", "tax_category_id"}
            )
            if self.bundle == "TREATMENT" and self.treatment in {"EXEMPT", "NON_GST"}:
                expected.add("exemption_reason")
        if fields != expected:
            raise ValueError("binding requires exactly its selected bundle and mode fields")
        return self


class ResolveInput(PricingInput):
    item_id: uuid.UUID
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    direction: Literal["SALE", "PURCHASE"]
    jurisdiction: Literal["IN"] = "IN"


class TaxQuery(ListQuery):
    is_active: bool | None = None
    item_kind: Literal["GOODS", "SERVICE"] | None = None
    treatment: Treatment | None = None
    tax_category_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    rate_id: uuid.UUID | None = None
    scope_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    activation_id: uuid.UUID | None = None
    release_id: uuid.UUID | None = None
    target_id: uuid.UUID | None = None
    direction: Literal["SALE", "PURCHASE"] | None = None
    bundle: Bundle | None = None
    code_system: Literal["HSN", "SAC"] | None = None
    as_of: dt.date | None = None


class SourcePin(PricingInput):
    entity_type: str
    entity_id: uuid.UUID
    entity_version: int


class BundleSource(PricingInput):
    bundle: Bundle
    scope_id: uuid.UUID
    owner_kind: str
    binding_id: uuid.UUID


class RateDefinition(PricingInput):
    applicability: Applicability
    rate_id: uuid.UUID
    source_reference: str
    source_url: str
    source_sha256: str
    components: list[ComponentInput]
    calculation_basis: Literal["TAXABLE_VALUE"] = "TAXABLE_VALUE"
    cess_levy: Literal["GST_COMPENSATION"] | None = None


class Resolution(PricingInput):
    item_id: uuid.UUID
    as_of: dt.date
    direction: Literal["SALE", "PURCHASE"]
    jurisdiction: Literal["IN"] = "IN"
    status: Literal["COMPLETE", "MISSING", "REQUIRE_EXPLICIT"]
    missing: list[str]
    classification_id: uuid.UUID | None = None
    classification_code: str | None = None
    treatment: Treatment | None = None
    exemption_reason: str | None = None
    rule_id: uuid.UUID | None = None
    tax_category_id: uuid.UUID | None = None
    rates: list[RateDefinition] = Field(default_factory=list)
    bundles: list[BundleSource] = Field(default_factory=list)
    sources: list[SourcePin] = Field(default_factory=list)
    policy_generation: int
    source_version: int
    transaction_determination_required: Literal[True] = True


class RatePreview(PricingInput):
    valid: bool = True
    series_id: uuid.UUID
    applicability: Applicability
    treatment: Treatment
    policy_generation: int
    source_version: int
    components: list[ComponentInput]


class TaxAdministrationContext(PricingInput):
    company_id: uuid.UUID
    country_code: str
    default_tax_system: str
    timezone: str
    business_date: dt.date
    policy_generation: int
    source_version: int
