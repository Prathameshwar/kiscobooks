"""Closed starter-pack inputs and bounded bootstrap result."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from catalog.schemas.pricing import ExactDecimal, PricingInput
from catalog.schemas.tax import CategoryInput, ClassificationMatch, Evidence


class StarterSource(PricingInput):
    reference: str = Field(min_length=1, max_length=400)
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def evidence(self) -> dict[str, str]:
        value = Evidence(
            source_reference=self.reference, source_url=self.url, source_sha256=self.sha256
        )
        return value.model_dump()


class StarterClassification(ClassificationMatch):
    item_kind: Literal["GOODS", "SERVICE"]
    description: str = Field(min_length=1, max_length=1000)
    source: str


class StarterRule(CategoryInput):
    category: str
    item_kind: Literal["GOODS", "SERVICE"]
    treatment: Literal["TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"]
    classification_scope: Literal["SPECIFIC", "ANY"] = "SPECIFIC"
    percentage: ExactDecimal = Field(ge=0, le=100)
    source: str
    classifications: list[ClassificationMatch] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def coherent_template(self) -> Self:
        if (self.classification_scope == "ANY") != (not self.classifications):
            raise ValueError("starter applicability must match its explicit classification scope")
        if (self.treatment == "TAXABLE") != (self.percentage > 0):
            raise ValueError("only taxable starter templates have a positive percentage")
        return self


class TaxStarterPack(PricingInput):
    version: str = Field(pattern=r"^[A-Z0-9_]{1,40}$")
    effective_from: dt.date
    reviewed_on: dt.date
    sources: dict[str, StarterSource]
    categories: list[CategoryInput] = Field(min_length=1, max_length=20)
    classifications: list[StarterClassification] = Field(min_length=1, max_length=128)
    rules: list[StarterRule] = Field(min_length=1, max_length=64)


class TaxDefaultsInput(PricingInput):
    pass


class TaxDefaultsResult(PricingInput):
    company_id: uuid.UUID
    pack_version: str
    status: Literal["READY", "NOT_APPLICABLE", "NEEDS_REVIEW"]
    categories_created: int = Field(0, ge=0)
    classifications_created: int = Field(0, ge=0)
    rules_created: int = Field(0, ge=0)
    rates_created: int = Field(0, ge=0)
    preserved_records: int = Field(0, ge=0)
    notices: list[str] = Field(default_factory=list, max_length=64)
