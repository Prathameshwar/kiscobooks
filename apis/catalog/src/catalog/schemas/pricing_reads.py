"""Protected native pricing projections; list rows omit terms and source evidence."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PricingDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    row_version: int | None = None


class PriceLevelDetail(PricingDetail):
    code: str | None = None
    name: str | None = None
    ordinal: int | None = None
    is_active: bool | None = None


class PriceLevelListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    code: str | None = None
    name: str | None = None
    ordinal: int | None = None
    is_active: bool | None = None


class PricePlanDetail(PricingDetail):
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    code: str | None = None
    name: str | None = None
    purpose: str | None = None
    price_level_id: uuid.UUID | None = None
    currency: str | None = None
    tax_basis: str | None = None


class PricePlanListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    code: str | None = None
    name: str | None = None
    purpose: str | None = None
    price_level_id: uuid.UUID | None = None
    currency: str | None = None
    tax_basis: str | None = None


class CompanyPricingPolicyDetail(PricingDetail):
    default_level_id: uuid.UUID | None = None
    missing_price_policy: str | None = None
    fallback_level_id: uuid.UUID | None = None
    purchase_plan_id: uuid.UUID | None = None
    sale_unit_mode: str | None = None
    purchase_unit_mode: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class CompanyPricingPolicyListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    default_level_id: uuid.UUID | None = None
    missing_price_policy: str | None = None
    fallback_level_id: uuid.UUID | None = None
    purchase_plan_id: uuid.UUID | None = None
    sale_unit_mode: str | None = None
    purchase_unit_mode: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class ItemPriceScopeDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    subject_kind: str | None = None
    lot_id: uuid.UUID | None = None
    lot_mrp: Decimal | None = None
    lot_currency: str | None = None
    lot_unit_id: uuid.UUID | None = None


class ItemPriceScopeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    subject_kind: str | None = None


class ItemPriceNumericRevisionDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    price_decimal_places: int | None = None
    price_increment: Decimal | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class ItemPriceNumericRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    price_decimal_places: int | None = None
    price_increment: Decimal | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class ItemPriceSeriesDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    plan_id: uuid.UUID | None = None
    price_scope_id: uuid.UUID | None = None
    audience_kind: str | None = None
    channel_code: str | None = None


class ItemPriceSeriesListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    plan_id: uuid.UUID | None = None
    price_scope_id: uuid.UUID | None = None
    audience_kind: str | None = None
    channel_code: str | None = None


class ItemPriceDraftDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    price_method: str | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    status: str | None = None


class ItemPriceDraftListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    series_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    price_method: str | None = None
    status: str | None = None


class ItemPriceDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    price_method: str | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    source_draft_id: uuid.UUID | None = None
    supersedes_id: uuid.UUID | None = None


class ItemPriceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    currency: str | None = None
    series_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    price_method: str | None = None
    amount: Decimal | None = None


class ItemPriceTierDetail(PricingDetail):
    draft_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    min_quantity: Decimal | None = None
    max_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None


class ItemPriceTierListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    draft_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    min_quantity: Decimal | None = None
    max_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None


class PurchasePriceTermDetail(PricingDetail):
    draft_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    gross_amount: Decimal | None = None
    discount_kind: str | None = None
    discount_value: Decimal | None = None
    currency: str | None = None


class PurchasePriceTermListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    draft_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    gross_amount: Decimal | None = None
    discount_kind: str | None = None
    discount_value: Decimal | None = None
    currency: str | None = None


class ItemReferenceCostDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    source_reference: str | None = None
    estimate_kind: str | None = None


class ItemReferenceCostListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    estimate_kind: str | None = None


class ItemMrpDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    source_reference: str | None = None
    jurisdiction: str | None = None


class ItemMrpListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    amount: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    jurisdiction: str | None = None


class ItemPriceFormulaDetail(PricingDetail):
    draft_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    recipe: str | None = None
    percentage: Decimal | None = None
    estimate_kind: str | None = None
    jurisdiction: str | None = None
    rounding_mode: str | None = None


class ItemPriceFormulaListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    draft_id: uuid.UUID | None = None
    price_id: uuid.UUID | None = None
    recipe: str | None = None
    percentage: Decimal | None = None
    estimate_kind: str | None = None
    jurisdiction: str | None = None
    rounding_mode: str | None = None


class CommercialPolicyScopeDetail(PricingDetail):
    owner_kind: str | None = None
    owner_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None


class CommercialPolicyScopeListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    owner_kind: str | None = None
    group_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None


class CommercialGuardRuleDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    rule_kind: str | None = None
    amount: Decimal | None = None
    percentage: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    estimate_kind: str | None = None
    severity: str | None = None
    source_reference: str | None = None


class CommercialGuardRuleListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    currency: str | None = None
    numeric_revision_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    rule_kind: str | None = None
    amount: Decimal | None = None
    percentage: Decimal | None = None
    price_basis_quantity: Decimal | None = None
    tax_basis: str | None = None
    estimate_kind: str | None = None
    severity: str | None = None


class DiscountCeilingDetail(PricingDetail):
    scope_id: uuid.UUID | None = None
    max_discount_pct: Decimal | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class DiscountCeilingListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    scope_id: uuid.UUID | None = None
    max_discount_pct: Decimal | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class ItemCommercialPolicyDetail(PricingDetail):
    item_id: uuid.UUID | None = None
    free_sale_allowed: bool | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class ItemCommercialPolicyListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    free_sale_allowed: bool | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
