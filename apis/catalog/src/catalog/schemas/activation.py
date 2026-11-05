"""Reviewed immediate activation and immutable definition evidence."""

import datetime as dt
import uuid

from pydantic import Field

from catalog.schemas.pricing import PricingInput
from catalog.schemas.tax import SourcePin
from catalog.schemas.units import ExpectedVersion


class ActivationInput(PricingInput):
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class ActivationCommit(ExpectedVersion):
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))
    expected_family_version: int = Field(strict=True, ge=1, le=2**31 - 1)
    preview_token: str = Field(min_length=1, max_length=8192)


class ActivationPreview(PricingInput):
    item_id: uuid.UUID
    as_of: dt.date
    expected_version: int
    expected_family_version: int
    eligible: bool
    missing: list[str]
    sources: list[SourcePin]
    policy_generation: int
    source_version: int
    preview_token: str
