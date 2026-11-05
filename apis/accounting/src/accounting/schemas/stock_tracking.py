"""Strict tracking registration inputs; clients cannot submit stock facts or quantities."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from voucher_execution.identifiers import (
    IdentifierInput as IdentifierInput,
)
from voucher_execution.identifiers import (
    IdentifierRequirement as IdentifierRequirement,
)
from voucher_execution.stock import Exact


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrackingSource(StrictInput):
    company_id: uuid.UUID
    item_id: uuid.UUID
    as_of: dt.date
    profile_revision_id: uuid.UUID
    lot_tracking: StrictBool
    serial_tracking: StrictBool
    expiry_required: StrictBool
    manufacture_date_required: StrictBool
    shelf_life_days: int | None = Field(default=None, ge=1, le=36500, strict=True)
    minimum_remaining_life_days: int | None = Field(default=None, ge=0, le=36500, strict=True)
    requirements: list[IdentifierRequirement] = Field(default_factory=list, max_length=2)
    normalization_version: Literal[1] = 1
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    base_unit_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def unique_identifier_types(self) -> TrackingSource:
        if len({value.identifier_type for value in self.requirements}) != len(self.requirements):
            raise ValueError("identifier requirements must use distinct types")
        return self


class Reason(StrictInput):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3 or any(ord(c) < 32 for c in value):
            raise ValueError("enter a printable reason of at least three characters")
        return value


class BatchPrepare(Reason):
    item_id: uuid.UUID
    code: str = Field(min_length=1, max_length=100)
    source_party_id: uuid.UUID | None = None
    manufactured_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    expires_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    mrp_amount: Exact | None = Field(default=None, gt=0)
    mrp_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    mrp_unit_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def dates(self) -> BatchPrepare:
        if (
            len({value is None for value in (self.mrp_amount, self.mrp_currency, self.mrp_unit_id)})
            != 1
        ):
            raise ValueError("MRP requires its amount, currency and declared unit together")
        if self.manufactured_on and self.expires_on and self.expires_on < self.manufactured_on:
            raise ValueError("expiry must not precede manufacture")
        return self


class ExpectedVersion(Reason):
    expected_version: int = Field(ge=1, strict=True)


class BatchCorrect(ExpectedVersion):
    manufactured_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    expires_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class SerialPrepare(Reason):
    item_id: uuid.UUID
    lot_id: uuid.UUID | None = None
    identifiers: list[IdentifierInput] = Field(min_length=1, max_length=16)


class SerialIdentityCheck(StrictInput):
    identifiers: list[IdentifierInput] = Field(min_length=1, max_length=3200)


class SerialIdentityCheckResult(StrictInput):
    available: Literal[True] = True


class BatchQuery(ListQuery):
    item_id: uuid.UUID | None = None
    status: Literal["ACTIVE", "RETIRED"] | None = None
    is_held: bool | None = None
    expires_before: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class SerialQuery(ListQuery):
    item_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    status: Literal["ACTIVE", "RETIRED"] | None = None
    is_held: bool | None = None
    never_received: bool = False
    receipt_eligible: bool = False
    source_movement_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def receipt_or_source(self) -> SerialQuery:
        if (
            sum((self.never_received, self.receipt_eligible, self.source_movement_id is not None))
            > 1
        ):
            raise ValueError("choose prepared receipt units or original movement units")
        return self


class TrackingListItem(StrictInput):
    id: uuid.UUID
    item_id: uuid.UUID | None = None
    status: Literal["ACTIVE", "RETIRED"] | None = None
    is_held: bool | None = None
    row_version: int | None = None


class BatchListItem(TrackingListItem):
    code: str | None = None
    manufactured_on: dt.date | None = None
    expires_on: dt.date | None = None
    source_party_id: uuid.UUID | None = None


class BatchDetail(BatchListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    operational_ready: Literal[False] = False
    mrp_amount: Exact | None = None
    mrp_currency: str | None = None
    mrp_unit_id: uuid.UUID | None = None


class SerialListItem(TrackingListItem):
    lot_id: uuid.UUID | None = None
    identifiers: list[IdentifierInput] | None = None


class SerialDetail(SerialListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    operational_ready: Literal[False] = False


class TrackingEventItem(StrictInput):
    id: uuid.UUID
    action: str
    reason: str | None = None
    created_at: dt.datetime
    created_by: uuid.UUID | None = None


class TrackingChange(StrictInput):
    field: str
    before: str | bool | None = None
    after: str | bool | None = None
    changed: bool = True


class TrackingEventDetail(TrackingEventItem):
    changes: list[TrackingChange]
