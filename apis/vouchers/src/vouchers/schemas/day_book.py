"""Bounded, read-only live document activity. Financial totals belong to Reports."""

import datetime as dt
import uuid
from typing import Literal, Self

from billing_platform.listing import PageMeta
from pydantic import Field, model_validator

from vouchers.schemas.configuration import Contract


class DayBookCondition(Contract):
    field: Literal["number", "narration", "kind"]
    operator: Literal["contains", "equals", "not_contains"] = "contains"
    value: str = Field(min_length=1, max_length=120)


class DayBookQuery(Contract):
    date_from: dt.date
    date_to: dt.date
    kinds: list[str] = Field(default_factory=list, max_length=30)
    type_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    status: str | None = Field(default=None, max_length=20)
    q: str = Field(default="", max_length=120)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    conditions: list[DayBookCondition] = Field(default_factory=list, max_length=8)
    match: Literal["ALL", "ANY"] = "ALL"
    sort: Literal["date", "-date", "number"] = "date"
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)
    include_summary: bool = False

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.date_from > self.date_to or (self.date_to - self.date_from).days > 3660:
            raise ValueError("choose an ordered period of at most ten years")
        if any(not item or len(item) > 40 for item in self.kinds):
            raise ValueError("invalid voucher kind")
        return self


class DayBookDocument(Contract):
    id: uuid.UUID
    voucher_id: uuid.UUID
    revision_id: uuid.UUID
    date: dt.date
    number: str | None
    kind: str
    type_id: uuid.UUID
    type_code: str
    type_name: str
    profile: str
    status: str
    narration: str
    currency: str
    particulars: str


class DayBookSummary(Contract):
    voucher_count: int
    by_status: dict[str, int]
    by_kind: dict[str, int]


class DayBookPage(Contract):
    items: list[DayBookDocument]
    page: PageMeta
    summary: DayBookSummary | None
    observed_at: dt.datetime
    scope: Literal["LIVE_DOCUMENTS"] = "LIVE_DOCUMENTS"


class DayBookTypeRevisions(Contract):
    type_id: uuid.UUID
    revision_ids: list[uuid.UUID]
