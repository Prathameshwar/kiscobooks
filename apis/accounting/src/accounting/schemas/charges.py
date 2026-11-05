"""Overdue charge policy and approval API contracts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field

from accounting.schemas.ledger import Amount, BusinessDate, Rate, exact_input
from accounting.schemas.masters import DecimalInput, Detail, ExpectedVersion, Input

NonnegativeAmount = Annotated[
    DecimalInput,
    BeforeValidator(exact_input),
    Field(ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
]


class ChargePolicyCreate(Input):
    account_id: uuid.UUID
    offset_account_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_from: BusinessDate
    valid_to: BusinessDate | None = None
    accrual_start_date: BusinessDate
    method: Literal["FIXED", "INTEREST"]
    rate: Amount
    rate_period: Literal["ANNUAL", "MONTHLY", "DAILY"] = "ANNUAL"
    compound: Literal["SIMPLE", "DAILY"] = "SIMPLE"
    basis: Literal["OUTSTANDING", "ORIGINAL"] = "OUTSTANDING"
    day_basis: Literal[360, 365] = 365
    grace_days: int = Field(default=0, strict=True, ge=0, le=3650)
    minimum: NonnegativeAmount = Decimal(0)
    cap: NonnegativeAmount | None = None
    charge_on_charge: bool = Field(default=False, strict=True)
    tax_treatment: Literal["NON_TAXABLE", "EXTERNAL"]
    tax_reason: str = Field(min_length=3, max_length=500)


class ChargePolicyClose(ExpectedVersion):
    valid_to: BusinessDate


class ChargeRequest(Input):
    item_id: uuid.UUID
    policy_id: uuid.UUID
    coverage_end_date: BusinessDate
    posting_date: BusinessDate
    due_date: BusinessDate
    exchange_rate: Rate
    external_reference: str | None = Field(default=None, min_length=1, max_length=120)


class ChargeApprove(ExpectedVersion):
    reason: str = Field(min_length=3, max_length=500)


class ChargePreview(Input):
    item_id: uuid.UUID
    policy_id: uuid.UUID
    coverage_start_date: dt.date
    coverage_end_date: dt.date
    currency: str
    amount: DecimalInput
    cumulative_amount: DecimalInput
    input_hash: str
    snapshot: dict[str, Any]


class ChargePolicyDetail(Detail):
    account_id: uuid.UUID | None = None
    offset_account_id: uuid.UUID | None = None
    currency: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    accrual_start_date: dt.date | None = None
    method: str | None = None
    rate: DecimalInput | None = None
    rate_period: str | None = None
    compound: str | None = None
    basis: str | None = None
    day_basis: int | None = None
    grace_days: int | None = None
    minimum: DecimalInput | None = None
    cap: DecimalInput | None = None
    charge_on_charge: bool | None = None
    tax_treatment: str | None = None
    tax_reason: str | None = None


class ChargePolicyListItem(Detail):
    account_id: uuid.UUID | None = None
    currency: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    method: str | None = None
    rate: DecimalInput | None = None


class ChargeAssessmentDetail(Detail):
    item_id: uuid.UUID | None = None
    policy_id: uuid.UUID | None = None
    status: str | None = None
    coverage_start_date: dt.date | None = None
    coverage_end_date: dt.date | None = None
    posting_date: dt.date | None = None
    due_date: dt.date | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    cumulative_amount: DecimalInput | None = None
    exchange_rate: DecimalInput | None = None
    external_reference: str | None = None
    journal_id: uuid.UUID | None = None
    input_hash: str | None = None
    snapshot: dict[str, Any] | None = None
    approved_by: uuid.UUID | None = None
    approved_at: dt.datetime | None = None
    reason: str | None = None


class ChargeAssessmentListItem(Detail):
    item_id: uuid.UUID | None = None
    policy_id: uuid.UUID | None = None
    status: str | None = None
    coverage_start_date: dt.date | None = None
    coverage_end_date: dt.date | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    journal_id: uuid.UUID | None = None
