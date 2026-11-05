"""Credit decisions, reservations and exception approval contracts."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from accounting.schemas.ledger import Amount, BusinessDate, Rate
from accounting.schemas.masters import DecimalInput, Detail, ExpectedVersion, Input


class CreditCheck(Input):
    account_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount
    exchange_rate: Rate
    posting_date: BusinessDate


class CreditRequest(CreditCheck):
    source_system: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    source_type: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    source_id: str = Field(min_length=1, max_length=120)
    expires_at: AwareDatetime
    override_id: uuid.UUID | None = None


class OverrideRequest(CreditRequest):
    reason: str = Field(min_length=3, max_length=500)


class CreditDecision(Input):
    status: Literal["ALLOW", "WARN", "BLOCK", "OVERRIDE_REQUIRED"]
    currency: str
    exposure: DecimalInput
    reserved: DecimalInput
    proposed: DecimalInput
    projected: DecimalInput
    limit: DecimalInput | None
    overdue: DecimalInput
    unknown_due: DecimalInput
    overdue_history_complete: bool
    reasons: list[str]
    policy_id: uuid.UUID | None
    policy_version: int | None
    assessed_date: dt.date


class OverrideApprove(ExpectedVersion):
    approve: bool = Field(strict=True)
    reason: str = Field(min_length=3, max_length=500)


class ReservationRenew(ExpectedVersion):
    expires_at: AwareDatetime
    posting_date: BusinessDate
    exchange_rate: Rate


class CreditOverrideDetail(Detail):
    account_id: uuid.UUID | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    source_system: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    status: str | None = None
    expires_at: dt.datetime | None = None
    reason: str | None = None
    approved_by: uuid.UUID | None = None
    approved_at: dt.datetime | None = None
    decision: dict[str, Any] | None = None


class CreditOverrideListItem(Detail):
    account_id: uuid.UUID | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    status: str | None = None
    expires_at: dt.datetime | None = None
    approved_by: uuid.UUID | None = None


class CreditReservationDetail(Detail):
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    base_currency: str | None = None
    base_amount: DecimalInput | None = None
    source_system: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    status: str | None = None
    expires_at: dt.datetime | None = None
    journal_id: uuid.UUID | None = None
    override_id: uuid.UUID | None = None
    decision: dict[str, Any] | None = None


class CreditReservationListItem(Detail):
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: str | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    status: str | None = None
    expires_at: dt.datetime | None = None
    journal_id: uuid.UUID | None = None
