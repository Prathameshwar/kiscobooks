"""Retained manual statutory evidence and native input-credit actions."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from accounting.schemas.ledger import Amount, BusinessDate
from accounting.schemas.masters import DecimalInput, Detail, Input


class CreditEvidenceInput(Input):
    document_verified: bool = Field(default=False, strict=True)
    supply_received: bool = Field(default=False, strict=True)
    business_use: bool = Field(default=False, strict=True)
    restrictions_checked: bool = Field(default=False, strict=True)
    supplier_report_matched: bool = Field(default=False, strict=True)
    tax_payment_verified: bool = Field(default=False, strict=True)
    return_filed: bool = Field(default=False, strict=True)
    supplier_paid: bool = Field(default=False, strict=True)
    reference: str = Field(min_length=1, max_length=500)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreditActionRequest(CreditEvidenceInput):
    component_id: uuid.UUID
    expected_event_id: uuid.UUID
    kind: Literal["VERIFY", "CLAIM", "BLOCK", "REVERSE_PAYMENT", "RECLAIM_PAYMENT", "RCM_DISCHARGE"]
    amount: Amount
    event_date: BusinessDate
    posting_date: BusinessDate
    annual_return_filed_on: dt.date | None = None
    offset_account_id: uuid.UUID | None = None
    cash_deposit_line_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=500)


class InvoiceCreditActionDetail(Detail):
    invoice_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    expected_event_id: uuid.UUID | None = None
    kind: str | None = None
    amount: DecimalInput | None = None
    event_date: dt.date | None = None
    posting_date: dt.date | None = None
    currency: str | None = None
    journal_id: uuid.UUID | None = None
    offset_account_id: uuid.UUID | None = None
    cash_deposit_line_id: uuid.UUID | None = None
    annual_return_filed_on: dt.date | None = None
    document_verified: bool | None = None
    supply_received: bool | None = None
    business_use: bool | None = None
    restrictions_checked: bool | None = None
    supplier_report_matched: bool | None = None
    tax_payment_verified: bool | None = None
    return_filed: bool | None = None
    supplier_paid: bool | None = None
    reference: str | None = None
    evidence_sha256: str | None = None
    reason: str | None = None


class InvoiceCreditEventDetail(Detail):
    invoice_id: uuid.UUID | None = None
    action_id: uuid.UUID | None = None


class InvoiceCreditPosition(Input):
    component_id: uuid.UUID
    latest_event_id: uuid.UUID
    currency: str
    recorded: DecimalInput
    pending: DecimalInput
    eligible_unclaimed: DecimalInput
    claimed: DecimalInput
    suspended: DecimalInput
    blocked: DecimalInput
    rcm_discharged: DecimalInput
