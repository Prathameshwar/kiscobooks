"""Closed inventory-specific inputs; a frozen generation supplies the evaluation timezone."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator
from reporting_contract.contract import Contract


class InventoryParameters(Contract):
    as_of: dt.date
    item_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    owner: Literal["OWN", "THIRD_PARTY"] | None = None
    include_inactive: bool = True


class StockPositionParameters(InventoryParameters):
    custody: Literal["LOCAL", "TRANSIT", "EXTERNAL"] | None = None


class LocationParameters(StockPositionParameters):
    search: str = Field(default="", max_length=120)


class GroupParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)


class LedgerParameters(StockPositionParameters):
    item_id: uuid.UUID
    date_from: dt.date
    lot_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def period(self) -> Self:
        if self.date_from > self.as_of:
            raise ValueError("date_from must not follow as_of")
        return self


class StockSummaryParameters(StockPositionParameters):
    search: str = Field(default="", max_length=120)
    include_zero: bool = True
    sort: Literal["ITEM_CODE", "ITEM_NAME", "QUANTITY", "VALUE"] = "ITEM_CODE"
    descending: bool = False


class ExpiryParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)
    days_ahead: int = Field(default=90, ge=0, le=3650)
    include_expired: bool = True


class BatchParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)
    lot_id: uuid.UUID | None = None
    include_history: bool = False
    serial: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def history_selection(self) -> Self:
        if self.serial is not None and not self.include_history:
            raise ValueError("a serial history filter requires include_history")
        return self


class ValuationParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)
    include_cost_details: bool = False


class AgeingParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)
    age_basis: Literal["RECEIPT", "MANUFACTURE"] = "RECEIPT"
    buckets: tuple[int, ...] = Field(default=(30, 60, 90, 180), min_length=1, max_length=8)

    @model_validator(mode="after")
    def intervals(self) -> Self:
        if not 1 <= len(self.buckets) <= 8 or (
            tuple(sorted(set(self.buckets))) != self.buckets
            or self.buckets[0] < 1
            or self.buckets[-1] > 36500
        ):
            raise ValueError("age buckets must be distinct positive ascending day limits")
        return self


class MovementParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)
    date_from: dt.date
    nonmoving_days: int = Field(default=90, ge=1, le=36500)
    only_nonmoving: bool = False

    @model_validator(mode="after")
    def period(self) -> Self:
        if self.date_from > self.as_of:
            raise ValueError("date_from must not follow as_of")
        return self


class ReorderParameters(InventoryParameters):
    search: str = Field(default="", max_length=120)
    quantity_basis: Literal["AVAILABLE", "ELIGIBLE"] = "AVAILABLE"
    only_shortages: bool = True
    include_orders: bool = False
