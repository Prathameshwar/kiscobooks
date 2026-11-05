"""Bounded resource queries and native form metadata."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field


class MasterQuery(ListQuery):
    code: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, pattern="^(DRAFT|ACTIVE|INACTIVE)$")
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"] | None = None
    party_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    head_id: uuid.UUID | None = None
    payment_term_id: uuid.UUID | None = None
    address_id: uuid.UUID | None = None
    registration_id: uuid.UUID | None = None
    as_of: dt.date | None = Field(None, ge=dt.date(1000, 1, 1))
    alias: str | None = Field(None, min_length=1, max_length=160)
    kind: str | None = Field(default=None, max_length=40)
    purpose: str | None = Field(default=None, max_length=40)
    direction: str | None = Field(default=None, pattern="^(SALE|PURCHASE)$")
    section_id: uuid.UUID | None = None
    deductee_type: str | None = Field(default=None, pattern="^[A-Z_]{1,40}$")


class AccountQuery(MasterQuery):
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    currency_mode: str | None = Field(default=None, pattern="^(BASE|FIXED|MULTI)$")


class HistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)
    sort: str | None = Field(default=None, min_length=1, max_length=200)


class FieldDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str
    required: bool
    visible: bool
    readable: bool
    writable: bool
    definition: dict[str, Any]
    reference: str | None = None


class FieldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource: str
    fields: list[FieldDescription]
