"""Current authoring control; no business-date or product override."""

import uuid

from pydantic import Field, StrictBool

from catalog.schemas.configuration import StrictInput


class ProductModeDetail(StrictInput):
    company_id: uuid.UUID
    product_family_sku_enabled: StrictBool
    row_version: int
    policy_generation: int


class ProductModeRequest(StrictInput):
    expected_version: int = Field(strict=True, ge=0, lt=2**31)
    expected_generation: int = Field(strict=True, ge=1, lt=2**63)
    product_family_sku_enabled: StrictBool
    change_reason: str = Field(min_length=1, max_length=250)


class ProductModePreview(ProductModeDetail):
    requested_enabled: bool
    blockers: list[str] = Field(max_length=8)
    preview_token: str


class ProductModeCommit(ProductModeRequest):
    preview_token: str = Field(min_length=1, max_length=8192)
