"""Explicit protected detail and lean list contracts for native tax/activation records."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Detail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class TaxRuleApplicabilityDetail(Detail):
    rule_id: uuid.UUID | None = None
    code_system: str | None = None
    code: str | None = None
    match_kind: str | None = None
    row_version: int | None = None


class TaxRuleApplicabilityListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    rule_id: uuid.UUID | None = None
    code_system: str | None = None
    code: str | None = None
    match_kind: str | None = None
    row_version: int | None = None


class TaxReleaseDetail(Detail):
    change_reason: str | None = None
    business_date: dt.date | None = None
    input_digest: str | None = None
    change_count: int | None = None
    row_version: int | None = None


class TaxReleaseListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    business_date: dt.date | None = None
    change_count: int | None = None
    row_version: int | None = None


class TaxHistoryActionDetail(Detail):
    resource: str | None = None
    target_id: uuid.UUID | None = None
    action: str | None = None
    previous_id: uuid.UUID | None = None
    previous_valid_to: dt.date | None = None
    release_id: uuid.UUID | None = None
    reason: str | None = None
    business_date: dt.date | None = None
    row_version: int | None = None


class TaxHistoryActionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    resource: str | None = None
    target_id: uuid.UUID | None = None
    action: str | None = None
    previous_id: uuid.UUID | None = None
    release_id: uuid.UUID | None = None
    business_date: dt.date | None = None
    row_version: int | None = None


class TaxClassificationDetail(Detail):
    jurisdiction: str | None = None
    code_system: str | None = None
    code: str | None = None
    item_kind: str | None = None
    description: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    source_reference: str | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    row_version: int | None = None


class TaxClassificationListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    jurisdiction: str | None = None
    code_system: str | None = None
    code: str | None = None
    item_kind: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    row_version: int | None = None


class HsnSacReferenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    code_system: str
    description: str
    chapter: str
    item_kind: str
    gst_rate_default: None = Field(
        default=None,
        deprecated=True,
        description="Use dated company tax rates; undated suggestions are not authoritative.",
    )


class HsnSacSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[HsnSacReferenceItem]
    count: int


class TaxCategoryDetail(Detail):
    code: str | None = None
    name: str | None = None
    is_active: bool | None = None
    row_version: int | None = None


class TaxCategoryListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    is_active: bool | None = None
    row_version: int | None = None


class TaxRuleDetail(Detail):
    classification_scope: str | None = None
    source_reference: str | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    code: str | None = None
    name: str | None = None
    tax_system: str | None = None
    jurisdiction: str | None = None
    item_kind: str | None = None
    treatment: str | None = None
    tax_category_id: uuid.UUID | None = None
    is_active: bool | None = None
    custom_fields: dict[str, Any] | None = None
    row_version: int | None = None


class TaxRuleListItem(BaseModel):
    classification_scope: str | None = None
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    tax_system: str | None = None
    jurisdiction: str | None = None
    item_kind: str | None = None
    treatment: str | None = None
    tax_category_id: uuid.UUID | None = None
    is_active: bool | None = None
    row_version: int | None = None


class TaxRateSeriesDetail(Detail):
    rule_id: uuid.UUID | None = None
    applicability: str | None = None
    row_version: int | None = None


class TaxRateSeriesListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    rule_id: uuid.UUID | None = None
    applicability: str | None = None
    row_version: int | None = None


class TaxRateDetail(Detail):
    series_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    supersedes_id: uuid.UUID | None = None
    source_reference: str | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    row_version: int | None = None


class TaxRateListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    series_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    supersedes_id: uuid.UUID | None = None
    row_version: int | None = None
    rule_code: str | None = None
    rule_name: str | None = None
    applicability: str | None = None


class TaxRateComponentDetail(Detail):
    rate_id: uuid.UUID | None = None
    component_key: str | None = None
    component: str | None = None
    kind: str | None = None
    percentage: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None
    unit_id: uuid.UUID | None = None
    basis_quantity: Decimal | None = None
    rounding_mode: str | None = None
    position: int | None = None
    row_version: int | None = None


class TaxRateComponentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    rate_id: uuid.UUID | None = None
    component_key: str | None = None
    component: str | None = None
    kind: str | None = None
    percentage: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None
    unit_id: uuid.UUID | None = None
    basis_quantity: Decimal | None = None
    rounding_mode: str | None = None
    position: int | None = None
    row_version: int | None = None


class CatalogTaxScopeDetail(Detail):
    owner_kind: str | None = None
    owner_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    row_version: int | None = None


class CatalogTaxScopeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    owner_kind: str | None = None
    owner_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    row_version: int | None = None


class CatalogTaxBindingDetail(Detail):
    scope_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    direction: str | None = None
    bundle: str | None = None
    mode: str | None = None
    classification_id: uuid.UUID | None = None
    treatment: str | None = None
    exemption_reason: str | None = None
    tax_category_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    item_kind: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    row_version: int | None = None


class CatalogTaxBindingListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    scope_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    direction: str | None = None
    bundle: str | None = None
    mode: str | None = None
    classification_id: uuid.UUID | None = None
    treatment: str | None = None
    tax_category_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    item_kind: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    row_version: int | None = None


class ItemActivationDetail(Detail):
    item_id: uuid.UUID | None = None
    adoption_id: uuid.UUID | None = None
    activated_on: dt.date | None = None
    source_version: int | None = None
    policy_generation: int | None = None
    preview_hash: str | None = None
    row_version: int | None = None


class ItemActivationListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    item_id: uuid.UUID | None = None
    adoption_id: uuid.UUID | None = None
    activated_on: dt.date | None = None
    source_version: int | None = None
    policy_generation: int | None = None
    row_version: int | None = None


class ItemActivationSourceDetail(Detail):
    activation_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    entity_version: int | None = None
    row_version: int | None = None


class ItemActivationSourceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    activation_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    entity_version: int | None = None
    row_version: int | None = None


class ItemInventoryProfileDetail(Detail):
    item_id: uuid.UUID | None = None
    base_unit_id: uuid.UUID | None = None
    template_revision_id: uuid.UUID | None = None
    identifier_profile_id: uuid.UUID | None = None
    lot_tracking: bool | None = None
    serial_tracking: bool | None = None
    expiry_required: bool | None = None
    manufacture_date_required: bool | None = None
    shelf_life_days: int | None = None
    minimum_remaining_life_days: int | None = None
    issue_strategy: str | None = None
    valuation_method: str | None = None
    negative_stock_policy: str | None = None
    row_version: int | None = None


class ItemInventoryProfileListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    item_id: uuid.UUID | None = None
    base_unit_id: uuid.UUID | None = None
    template_revision_id: uuid.UUID | None = None
    identifier_profile_id: uuid.UUID | None = None
    lot_tracking: bool | None = None
    serial_tracking: bool | None = None
    expiry_required: bool | None = None
    manufacture_date_required: bool | None = None
    shelf_life_days: int | None = None
    minimum_remaining_life_days: int | None = None
    issue_strategy: str | None = None
    valuation_method: str | None = None
    negative_stock_policy: str | None = None
    row_version: int | None = None
