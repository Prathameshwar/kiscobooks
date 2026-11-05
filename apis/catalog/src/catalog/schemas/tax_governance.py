"""Typed coordinated tax publication and future correction contracts."""

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from catalog.schemas.pricing import DatedInput, PricingInput, PublicationInput
from catalog.schemas.tax import BindingInput, Bundle, ClassificationInput, RateInput, Treatment


class NewClassification(PricingInput):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")


class ReleaseBinding(DatedInput):
    scope_id: uuid.UUID
    jurisdiction: Literal["IN"] = "IN"
    direction: Literal["SALE", "PURCHASE"]
    bundle: Bundle
    mode: Literal["INHERIT", "OVERRIDE", "REQUIRE_EXPLICIT"]
    classification_id: uuid.UUID | NewClassification | None = None
    treatment: Treatment | None = None
    exemption_reason: str | None = Field(default=None, min_length=1, max_length=500)
    tax_category_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    item_kind: Literal["GOODS", "SERVICE"] | None = None

    @model_validator(mode="after")
    def valid_bundle(self) -> Self:
        value = self.model_dump()
        if isinstance(self.classification_id, NewClassification):
            # Validate the ordinary shape; the actual scoped ID is resolved inside the release.
            value["classification_id"] = uuid.UUID(int=1)
        BindingInput.model_validate(value)
        return self


class Change(PricingInput):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")


class ClassificationChange(Change):
    kind: Literal["CLASSIFICATION"]
    definition: ClassificationInput


class RateChange(Change):
    kind: Literal["RATE"]
    definition: RateInput


class BindingChange(Change):
    kind: Literal["BINDING"]
    definition: ReleaseBinding


class WithdrawalInput(PublicationInput):
    resource: Literal["tax_classification", "tax_rate", "catalog_tax_binding"]
    target_id: uuid.UUID
    expected_version: int = Field(strict=True, ge=1, le=2**31 - 1)
    reason: str = Field(min_length=1, max_length=500)
    restore_predecessor: StrictBool = True


class WithdrawalChange(Change):
    kind: Literal["WITHDRAWAL"]
    definition: WithdrawalInput


TaxChange = Annotated[
    ClassificationChange | RateChange | BindingChange | WithdrawalChange,
    Field(discriminator="kind"),
]


class ReleaseInput(PublicationInput):
    change_reason: str = Field(min_length=1, max_length=500)
    changes: list[TaxChange] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len({entry.key for entry in self.changes}) != len(self.changes):
            raise ValueError("tax change keys must be distinct")
        for entry in self.changes:
            if (
                entry.definition.expected_generation != self.expected_generation
                or entry.definition.expected_source_version != self.expected_source_version
            ):
                raise ValueError("all changes must use the reviewed generation and source version")
        return self


class ReleaseCommit(ReleaseInput):
    """Publishes against exactly one review: a synchronous preview or a background report."""

    preview_token: str | None = Field(default=None, min_length=1, max_length=2000)
    impact_review_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_review(self) -> Self:
        if (self.preview_token is None) == (self.impact_review_id is None):
            raise ValueError("provide exactly one of preview_token or impact_review_id")
        return self


class ImpactItem(PricingInput):
    item_id: uuid.UUID
    direction: Literal["SALE", "PURCHASE"]
    as_of: dt.date
    status: Literal["COMPLETE", "MISSING", "REQUIRE_EXPLICIT", "INVALID"]
    missing: list[str]


class ReleasePreview(PricingInput):
    valid: Literal[True] = True
    policy_generation: int
    source_version: int
    affected_item_ids: list[uuid.UUID]
    checked_dates: list[dt.date]
    impact: list[ImpactItem]
    preview_token: str


class ImpactQuery(PricingInput):
    resource: Literal["tax_classification", "tax_rule", "catalog_tax_scope"]
    target_id: uuid.UUID
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class TaxImpact(PricingInput):
    affected_item_ids: list[uuid.UUID]
    checked_dates: list[dt.date]
    impact: list[ImpactItem]


ReviewStatus = Literal["PENDING", "COMPLETE", "STALE", "FAILED"]


class ImpactReviewDetail(BaseModel):
    """Report metadata; the reviewed request body itself stays internal."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    status: ReviewStatus
    change_reason: str
    change_count: int
    input_digest: str
    policy_generation: int
    source_version: int
    business_date: dt.date
    item_count: int
    checked_count: int
    finding_count: int
    blocking_count: int
    reason_code: str | None
    completed_at: dt.datetime | None
    created_at: dt.datetime
    row_version: int


class ImpactFindingQuery(ListQuery):
    blocking: bool | None = None


class ImpactFindingListItem(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: uuid.UUID
    item_id: uuid.UUID
    direction: Literal["SALE", "PURCHASE"]
    as_of: dt.date
    status: Literal["MISSING", "REQUIRE_EXPLICIT", "INVALID"]
    missing: list[str]
    blocking: bool
