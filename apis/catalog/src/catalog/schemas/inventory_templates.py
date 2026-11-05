"""Typed inventory template requirements and lean history projections."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from catalog.domain.profiles import InventoryRules
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import ExpectedVersion

IssueStrategy = Literal["FIFO", "FEFO"]
ValuationMethod = Literal["FIFO", "MOVING_AVERAGE", "SPECIFIC"]
NegativeStockPolicy = Literal["BLOCK", "WARN", "ALLOW"]


class InventoryTemplateCreate(MasterInput):
    pass


class InventoryTemplateUpdate(MasterUpdate):
    pass


class InventoryTemplateListItem(MasterListItem):
    pass


class InventoryTemplateDetail(InventoryTemplateListItem, DetailFields):
    pass


class InventoryTemplateQuery(MasterQuery):
    pass


class InventoryRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier_profile_id: uuid.UUID | None = None
    lot_tracking: StrictBool = False
    serial_tracking: StrictBool = False
    expiry_required: StrictBool = False
    manufacture_date_required: StrictBool = False
    shelf_life_days: int | None = Field(default=None, ge=1, le=36500, strict=True)
    minimum_remaining_life_days: int | None = Field(default=None, ge=0, le=36500, strict=True)
    issue_strategy: IssueStrategy = "FIFO"
    valuation_method: ValuationMethod = "FIFO"
    negative_stock_policy: NegativeStockPolicy = "BLOCK"

    @model_validator(mode="after")
    def coherent(self) -> "InventoryRevisionInput":
        InventoryRules(
            self.lot_tracking,
            self.serial_tracking,
            self.expiry_required,
            self.manufacture_date_required,
            self.shelf_life_days,
            self.minimum_remaining_life_days,
            self.issue_strategy,
            self.valuation_method,
            self.identifier_profile_id is not None,
            self.negative_stock_policy,
        )
        return self


class InventoryRevisionUpdate(ExpectedVersion):
    identifier_profile_id: uuid.UUID | None = None
    lot_tracking: StrictBool | None = None
    serial_tracking: StrictBool | None = None
    expiry_required: StrictBool | None = None
    manufacture_date_required: StrictBool | None = None
    shelf_life_days: int | None = Field(default=None, ge=1, le=36500, strict=True)
    minimum_remaining_life_days: int | None = Field(default=None, ge=0, le=36500, strict=True)
    issue_strategy: IssueStrategy | None = None
    valuation_method: ValuationMethod | None = None
    negative_stock_policy: NegativeStockPolicy | None = None

    @model_validator(mode="after")
    def no_null_requirements(self) -> "InventoryRevisionUpdate":
        nullable = {"identifier_profile_id", "shelf_life_days", "minimum_remaining_life_days"}
        if any(getattr(self, name) is None for name in self.model_fields_set - nullable):
            raise ValueError("inventory flags and strategies cannot be cleared")
        return self


class InventoryRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    template_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    published_at: dt.datetime | None = None
    lot_tracking: bool | None = None
    serial_tracking: bool | None = None
    expiry_required: bool | None = None
    issue_strategy: IssueStrategy | None = None
    valuation_method: ValuationMethod | None = None
    negative_stock_policy: NegativeStockPolicy | None = None


class InventoryRevisionDetail(InventoryRevisionListItem, DetailFields):
    identifier_profile_id: uuid.UUID | None = None
    manufacture_date_required: bool | None = None
    shelf_life_days: int | None = None
    minimum_remaining_life_days: int | None = None


class InventoryRevisionQuery(ListQuery):
    published: bool | None = None
    lot_tracking: bool | None = None
    serial_tracking: bool | None = None
    expiry_required: bool | None = None
    identifier_profile_id: uuid.UUID | None = None
    issue_strategy: IssueStrategy | None = None
    valuation_method: ValuationMethod | None = None
    negative_stock_policy: NegativeStockPolicy | None = None
