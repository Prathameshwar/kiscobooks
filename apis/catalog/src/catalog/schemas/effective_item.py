"""Protected, dated Catalog-owned item facts and execution-readiness boundary."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer

from catalog.schemas.configuration import EffectiveConfiguration
from catalog.schemas.product_authoring import ProductRequirements
from catalog.schemas.regulatory import EffectiveRegulatoryClassification


class InventorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_revision_id: uuid.UUID
    valuation_method: Literal["FIFO", "MOVING_AVERAGE", "SPECIFIC"]
    negative_stock_policy: Literal["BLOCK", "WARN", "ALLOW"]
    issue_strategy: Literal["FIFO", "FEFO"]
    lot_tracking: bool
    serial_tracking: bool
    identifier_profile_id: uuid.UUID | None
    expiry_required: bool
    manufacture_date_required: bool
    shelf_life_days: int | None
    minimum_remaining_life_days: int | None


class StockExecutionReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["NOT_APPLICABLE", "UNAVAILABLE"]
    reasons: list[str]


class EffectiveUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_id: uuid.UUID
    revision_id: uuid.UUID
    revision: int
    unit_id: uuid.UUID
    usage_role: Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK", "MEASURED"]
    valid_from: dt.date
    valid_to: dt.date | None
    conversion_mode: Literal["FIXED", "MEASURED"]
    numerator: int | None
    denominator: int | None
    nominal_ratio: Decimal | None
    quantity_decimal_places: int
    quantity_increment: Decimal
    fractional_entry: bool

    @field_serializer("numerator", "denominator")
    def ratio_wire(self, value: int | None) -> str | None:
        return str(value) if value is not None else None


class EffectiveItemFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    item_id: uuid.UUID
    family_id: uuid.UUID
    as_of: dt.date
    kind: Literal["GOODS", "SERVICE"]
    item_status: Literal["DRAFT", "ACTIVE", "DISCONTINUED"]
    item_version: int
    family_version: int
    product_type_revision_id: uuid.UUID
    group_id: uuid.UUID | None
    group_assignment_id: uuid.UUID | None
    base_unit_id: uuid.UUID
    units: list[EffectiveUnit]
    sellable: bool
    purchasable: bool
    min_sale_quantity: Decimal | None
    configuration: EffectiveConfiguration
    requirements: ProductRequirements
    inventory: InventorySelection | None
    regulatory: EffectiveRegulatoryClassification | None
    stock_execution: StockExecutionReadiness
