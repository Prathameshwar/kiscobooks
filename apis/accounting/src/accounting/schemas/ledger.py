"""Typed journal inputs and field-protected financial outputs."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, SerializerFunctionWrapHandler, model_serializer

from accounting.schemas.masters import DecimalInput, Detail, ExpectedVersion, Input
from accounting.schemas.query import MasterQuery
from accounting.schemas.voucher_tax import VoucherTax


def exact_input(value: Any) -> Any:
    if isinstance(value, float | bool):
        raise ValueError("financial amounts require exact decimal strings")
    return value


Amount = Annotated[
    DecimalInput,
    BeforeValidator(exact_input),
    Field(gt=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
]
Rate = Annotated[
    DecimalInput,
    BeforeValidator(exact_input),
    Field(gt=0, max_digits=19, decimal_places=8, allow_inf_nan=False),
]
BusinessDate = Annotated[dt.date, Field(ge=dt.date(1000, 1, 1), le=dt.date(9999, 12, 31))]
JournalStatus = Literal["DRAFT", "PREPARED", "POSTED", "VOID"]
JournalKind = Literal[
    "MANUAL",
    "VOUCHER",
    "TAX_ACTION",
    "OPENING",
    "INVOICE",
    "BILL",
    "RECEIPT",
    "PAYMENT",
    "CREDIT_NOTE",
    "CHARGE",
    "REVERSAL",
    "REALIZED_FX",
]


class JournalLineCreate(Input):
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount
    exchange_rate: Rate
    description: str | None = Field(default=None, max_length=500)
    opening_base_amount: Amount | None = None

    @model_serializer(mode="wrap")
    def legacy_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.opening_base_amount is None:
            result.pop("opening_base_amount", None)
        return result


class JournalCreate(Input):
    document_date: BusinessDate
    posting_date: BusinessDate
    description: str = Field(min_length=3, max_length=1000)
    lines: list[JournalLineCreate] = Field(min_length=2, max_length=200)
    #: GST on the lines whose accounts carry a tax default; tax lines are generated.
    tax: VoucherTax | None = None


class JournalUpdate(JournalCreate, ExpectedVersion):
    pass


class JournalReverse(Input):
    posting_date: BusinessDate
    reason: str = Field(min_length=3, max_length=1000)


class JournalVoid(ExpectedVersion):
    reason: str = Field(min_length=3, max_length=500)


class JournalDetail(Detail):
    kind: JournalKind | None = None
    status: JournalStatus | None = None
    document_date: dt.date | None = None
    posting_date: dt.date | None = None
    description: str | None = None
    base_currency: str | None = None
    total_debit: DecimalInput | None = None
    total_credit: DecimalInput | None = None
    source_system: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    source_hash: str | None = None
    number: str | None = None
    fiscal_period_id: uuid.UUID | None = None
    authorization_journal_id: uuid.UUID | None = None
    reversal_of_id: uuid.UUID | None = None
    configuration_hash: str | None = None
    features: list[str] | None = None
    prepared_at: dt.datetime | None = None
    prepared_by: uuid.UUID | None = None
    prepared_version: int | None = None
    reservation_id: uuid.UUID | None = None
    posted_at: dt.datetime | None = None


class JournalListItem(Detail):
    kind: JournalKind | None = None
    status: JournalStatus | None = None
    posting_date: dt.date | None = None
    number: str | None = None
    base_currency: str | None = None
    total_debit: DecimalInput | None = None
    total_credit: DecimalInput | None = None


class JournalLineDetail(Detail):
    component: Literal["PRINCIPAL", "FX"] | None = None
    journal_id: uuid.UUID | None = None
    sequence: int | None = None
    account_id: uuid.UUID | None = None
    side: Literal["DEBIT", "CREDIT"] | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    exchange_rate: DecimalInput | None = None
    base_currency: str | None = None
    base_amount: DecimalInput | None = None
    party_id: uuid.UUID | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None
    description: str | None = None


class JournalLineListItem(Detail):
    component: Literal["PRINCIPAL", "FX"] | None = None
    journal_id: uuid.UUID | None = None
    sequence: int | None = None
    account_id: uuid.UUID | None = None
    side: Literal["DEBIT", "CREDIT"] | None = None
    currency: str | None = None
    amount: DecimalInput | None = None
    exchange_rate: DecimalInput | None = None
    base_currency: str | None = None
    base_amount: DecimalInput | None = None
    party_id: uuid.UUID | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None


class JournalQuery(MasterQuery):
    status: JournalStatus | None = None
    journal_id: uuid.UUID | None = None
    posting_date: BusinessDate | None = None
    source_system: str | None = Field(default=None, max_length=40)
    source_type: str | None = Field(default=None, max_length=40)
    source_id: str | None = Field(default=None, max_length=120)
    fiscal_period_id: uuid.UUID | None = None


class JournalPreviewLine(Input):
    sequence: int
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str
    amount: DecimalInput
    exchange_rate: DecimalInput
    base_currency: str
    base_amount: DecimalInput


class JournalPreview(Input):
    base_currency: str
    total_debit: DecimalInput
    total_credit: DecimalInput
    lines: list[JournalPreviewLine]


class BalanceQuery(Input):
    basis: Literal["BASE", "ORIGINAL"] = "BASE"
    as_of: BusinessDate
    account_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Balance(Input):
    as_of: dt.date
    currency: str
    debit: DecimalInput
    credit: DecimalInput
    balance: DecimalInput
