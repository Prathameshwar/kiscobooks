"""Fixed defaults consume signed company features, never browser-authored rules."""

import uuid
from typing import Literal

from pydantic import Field, field_serializer

from vouchers.schemas.configuration import Contract

Feature = Literal["inventory", "bom_definitions", "approval_workflow", "multi_currency"]


class DefaultsCreate(Contract):
    expected_features: frozenset[Feature] | None = Field(default=None, max_length=4)


class DefaultsResult(Contract):
    company_id: uuid.UUID
    catalogue_version: str
    status: Literal["READY", "NEEDS_REVIEW"]
    created_count: int = Field(ge=0, le=64)
    updated_count: int = Field(ge=0, le=64)
    preserved_count: int = Field(ge=0, le=64)
    review_count: int = Field(ge=0, le=64)
    features: frozenset[Feature] = Field(max_length=4)

    @field_serializer("features", when_used="json")
    def ordered_features(self, value: frozenset[Feature]) -> list[Feature]:
        return sorted(value)
