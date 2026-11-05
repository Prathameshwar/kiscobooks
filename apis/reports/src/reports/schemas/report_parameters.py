"""Report-specific v2 inputs: unsupported filters are errors, never ignored hints."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator
from reporting_contract.contract import Contract


class SourceParameters(Contract):
    """The diagnostic always covers the entire owner snapshot."""


class DateRange(Contract):
    date_from: dt.date
    date_to: dt.date

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not follow date_to")
        return self


class Comparison(Contract):
    comparative_from: dt.date | None = None
    comparative_to: dt.date | None = None

    @model_validator(mode="after")
    def ordered_comparison(self) -> Self:
        if (self.comparative_from is None) != (self.comparative_to is None):
            raise ValueError("both comparative dates are required")
        if (
            self.comparative_from
            and self.comparative_to
            and self.comparative_from > self.comparative_to
        ):
            raise ValueError("invalid comparative date range")
        return self


class CurrencyBasis(Contract):
    basis: Literal["BASE", "TRANSACTION"] = "BASE"
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def single_currency(self) -> Self:
        if (self.basis == "TRANSACTION") != (self.currency is not None):
            raise ValueError("only transaction basis requires a selected currency")
        return self


class AccountFilters(Contract):
    account_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None


class LedgerParameters(DateRange, CurrencyBasis, AccountFilters, Comparison):
    journal_id: uuid.UUID | None = None


class StatementParameters(DateRange, Comparison):
    """Statements always include all contributing base-currency accounts."""


class ProfitParameters(StatementParameters):
    show_zero: bool = False


class BalanceSheetParameters(SourceParameters):
    """Complete-company balances at one or two dates."""

    date_to: dt.date
    comparative_to: dt.date | None = None
    show_zero: bool = False

    @model_validator(mode="after")
    def earlier_comparison(self) -> Self:
        if self.comparative_to and self.comparative_to >= self.date_to:
            raise ValueError("comparison date must precede the as-of date")
        return self


class ContinuityParameters(DateRange):
    """The exact next-year calendar span, verified against the frozen company source."""


class SummaryParameters(DateRange, CurrencyBasis, AccountFilters, Comparison):
    grain: Literal["DAY", "MONTH"] = "DAY"


class AsOfParameters(CurrencyBasis, AccountFilters):
    date_to: dt.date


class BankReconciliationParameters(SourceParameters, CurrencyBasis):
    date_to: dt.date
    account_id: uuid.UUID
    statement_balance: str = Field(pattern=r"^-?\d{1,15}(\.\d{1,4})?$")


class BankWorklistParameters(DateRange):
    account_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    basis: Literal["TRANSACTION"] = "TRANSACTION"


class BankEvidenceParameters(BankWorklistParameters):
    session_id: uuid.UUID


class InvoiceParameters(DateRange, AccountFilters, Comparison):
    # Invoice amounts are native document currency; base GL amounts are separate columns.
    invoice_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class InvoiceSettlementParameters(SourceParameters, AccountFilters):
    """Cumulative allocation history with activity evaluated at the selected date."""

    date_to: dt.date
    comparative_to: dt.date | None = None
    invoice_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def earlier_comparison(self) -> Self:
        if self.comparative_to and self.comparative_to >= self.date_to:
            raise ValueError("comparison date must precede the as-of date")
        return self


class InvoiceDocumentParameters(InvoiceParameters):
    date_basis: Literal["POSTING", "DOCUMENT"] = "POSTING"


class InvoiceTaxParameters(InvoiceParameters):
    search: str = Field(default="", max_length=200)
    tax_code: str | None = Field(default=None, min_length=1, max_length=64)
    date_basis: Literal["POSTING", "DOCUMENT", "TAX_POINT"] = "POSTING"
    company_registration_id: uuid.UUID | None = None


class InvoiceCreditParameters(InvoiceParameters):
    search: str = Field(default="", max_length=200)
    tax_code: str | None = Field(default=None, min_length=1, max_length=64)
    company_registration_id: uuid.UUID | None = None


class TaxBridgeParameters(InvoiceCreditParameters):
    date_basis: Literal["POSTING", "TAX_POINT"] = "POSTING"
    tax_ledger_id: uuid.UUID | None = None
    tax_purpose: str | None = Field(default=None, min_length=1, max_length=64)
