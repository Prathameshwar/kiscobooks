"""Typed manual bank evidence; no payment provider or raw card data."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import PageMeta
from pydantic import Field

from accounting.schemas.masters import DecimalInput, Detail, Input


class BankInstrumentDetail(Detail):
    intent_id: uuid.UUID | None = None
    journal_line_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    tender_key: uuid.UUID | None = None
    mode: str | None = None
    reference: str | None = None
    instrument_date: dt.date | None = None
    booking_date: dt.date | None = None
    recognition: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None


class BankEventRequest(Input):
    expected_event_id: uuid.UUID
    action: Literal["PRESENTED", "CLEARED", "DISHONOURED", "RECONCILED", "UNRECONCILED"]
    event_date: dt.date
    reference: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str = Field(min_length=3, max_length=500)


class BankEventCommand(BankEventRequest):
    instrument_id: uuid.UUID


class BankEventDetail(Detail):
    instrument_id: uuid.UUID | None = None
    action: str | None = None
    event_date: dt.date | None = None
    reference: str | None = None
    reason: str | None = None


class BankAdoptRequest(Input):
    journal_line_id: uuid.UUID
    expected_journal_version: int = Field(ge=1)
    mode: Literal["CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"]
    reference: str = Field(min_length=1, max_length=120)
    instrument_date: dt.date | None = None
    evidence_date: dt.date
    reason: str = Field(min_length=3, max_length=500)


class BankInstrumentListItem(Input):
    id: uuid.UUID
    account_id: uuid.UUID | None = None
    booking_date: dt.date | None = None
    mode: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None


class BankInstrumentPage(Input):
    items: list[BankInstrumentListItem]
    page: PageMeta


class BankEventPage(Input):
    items: list[BankEventDetail]
    page: PageMeta


class BankHistoryQuery(Input):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)


class BankInstrumentQuery(BankHistoryQuery):
    account_id: uuid.UUID | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
