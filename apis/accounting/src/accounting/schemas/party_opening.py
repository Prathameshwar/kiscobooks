"""Opening-balance columns of a ready customer/supplier import and the staged-balance reads."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import Field, model_validator

from accounting.schemas.ledger import Amount, BusinessDate, Rate
from accounting.schemas.masters import ExpectedVersion, Input, PartyCreate

BalanceType = Literal["DR", "CR", "TO_RECEIVE", "TO_PAY"]


class ReadyPartyCreate(PartyCreate):
    """A party row. Every `opening_*` column is optional; leave them all empty for no balance.

    The balance is held for the opening declaration and never posted by the import. Giving any
    opening column also creates the party's ledger account, so the balance has somewhere to sit.
    Which columns belong together is checked by the opening rules, so each error names its column.
    """

    code: str = Field(..., min_length=1, max_length=40)

    opening_balance_type: BalanceType | None = Field(
        None,
        title="Opening balance type",
        description=(
            "DR or TO_RECEIVE is a debit balance (they owe you); "
            "CR or TO_PAY is a credit balance (you owe them)."
        ),
    )
    opening_amount: Amount | None = Field(
        None,
        title="Opening amount",
        description="Outstanding amount at the books begin date, positive, up to four decimals.",
    )
    opening_currency: str | None = Field(
        None,
        pattern=r"^[A-Z]{3}$",
        title="Opening currency",
        description="Three-letter currency code. Leave empty for the company currency.",
    )
    opening_exchange_rate: Rate | None = Field(
        None,
        title="Opening exchange rate",
        description="Required only for a foreign-currency balance.",
    )
    opening_base_amount: Amount | None = Field(
        None,
        title="Opening base amount",
        description=(
            "Historical carrying value in company currency. "
            "Required only for a foreign-currency balance."
        ),
    )
    opening_account_code: str | None = Field(
        None,
        min_length=1,
        max_length=40,
        title="Ledger account code",
        description="Code of the party's new ledger account. Defaults to the party code.",
    )
    opening_bill_reference: str | None = Field(
        None,
        min_length=1,
        max_length=120,
        title="Bill reference",
        description=(
            "Optional. With the bill date and due date it records one dated bill; "
            "without them the balance is held on account with dates unknown."
        ),
    )
    opening_bill_date: BusinessDate | None = Field(None, title="Bill date")
    opening_bill_due_date: BusinessDate | None = Field(None, title="Bill due date")


OPENING_FIELDS = frozenset(
    name for name in ReadyPartyCreate.model_fields if name.startswith("opening_")
)


class PartyOpeningQuery(ListQuery):
    status: Literal["PENDING", "WITHDRAWN"] | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None
    party_id: uuid.UUID | None = None


class PartyOpeningItem(Input):
    id: uuid.UUID
    row_version: int
    party_id: uuid.UUID
    role: Literal["CUSTOMER", "SUPPLIER"]
    account_id: uuid.UUID
    source_key: str
    status: Literal["PENDING", "WITHDRAWN"]
    side: Literal["DEBIT", "CREDIT"]
    currency: str
    amount: str
    exchange_rate: str
    base_amount: str
    document_kind: str | None
    document_reference: str
    document_date: dt.date | None
    due_date: dt.date | None
    included: bool


class PartyOpeningWithdraw(ExpectedVersion):
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def printable(self) -> "PartyOpeningWithdraw":
        if len(self.reason.strip()) < 3 or any(ord(char) < 32 for char in self.reason):
            raise ValueError("enter a printable reason of at least three characters")
        return self
