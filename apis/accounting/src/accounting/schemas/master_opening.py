"""Optional opening entered and posted during master creation."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.listing import ListQuery
from pydantic import Field

from accounting.schemas.financial_opening import OpeningDocument
from accounting.schemas.ledger import Amount, BusinessDate, Rate
from accounting.schemas.masters import AccountCreate, Input


class MasterOpeningInput(Input):
    amount: Amount = Field(gt=0, title="Opening balance")
    side: Literal["DEBIT", "CREDIT"] = Field(title="Dr / Cr")
    opening_date: BusinessDate = Field(title="Opening date")
    documents: list[OpeningDocument] = Field(default_factory=list, max_length=200)
    exchange_rate: Rate | None = Field(None, gt=0)
    base_amount: Amount | None = Field(None, gt=0)
    credit_cash_reason: str | None = Field(None, min_length=3, max_length=500)


class AccountCreation(AccountCreate):
    opening: MasterOpeningInput | None = None
    bank_profile: "CreationBankProfile | None" = None
    tax_profile: "CreationTaxProfile | None" = None


class CreationBankProfile(Input):
    company_bank_id: uuid.UUID
    reconciliation_start_date: dt.date | None = None


class CreationTaxProfile(Input):
    company_registration_id: uuid.UUID | None = None
    scheme: Literal["GST_IN", "VAT", "OTHER"]
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS", "VAT", "OTHER"]
    purpose: Literal[
        "INPUT_RECOVERABLE",
        "INPUT_PENDING",
        "OUTPUT_PAYABLE",
        "RCM_PAYABLE",
        "DEPOSIT",
        "ADJUSTMENT",
    ]
    duty_type: Literal["GST", "VAT", "TDS", "TCS", "CESS", "EXCISE", "OTHER"] = "OTHER"


AccountCreation.model_rebuild()


class MasterOpeningCapture(Input):
    company_id: uuid.UUID
    opening_date: dt.date
    currency: str
    can_capture: bool
    blockers: list[str]
    capture: dict[str, Any]
    capture_permissions: dict[str, dict[str, bool]]


class MasterOpeningQuery(ListQuery):
    limit: int = Field(20, ge=1, le=50)
    status: Literal["PENDING", "WITHDRAWN", "POSTING", "POSTED", "REVERSED"] | None = None
    account_id: uuid.UUID | None = None


class MasterOpeningDocument(Input):
    """Explicit read contract; the legacy bill serializer omits nullable fields."""

    line_sequence: int
    reference: str
    amount: Amount
    original_amount: Amount | None = None
    base_amount: Amount
    document_kind: Literal["ON_ACCOUNT", "INVOICE", "BILL", "CREDIT_NOTE", "ADVANCE"]
    document_date: dt.date | None = None
    due_date: dt.date | None = None
    source_key: str | None = None


class MasterOpeningEntry(Input):
    source_key: str
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str
    amount: Amount
    exchange_rate: Rate
    base_amount: Amount
    description: str | None = None
    documents: list[MasterOpeningDocument]


class MasterOpeningItem(Input):
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    account_id: uuid.UUID
    source_key: str
    status: Literal["PENDING", "WITHDRAWN", "POSTING", "POSTED", "REVERSED"]
    opening_date: dt.date
    entry: MasterOpeningEntry
    included: bool
