import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from billing_platform.listing import PageMeta
from pydantic import Field, model_validator
from reporting_contract.contract import Contract


class GenerationRequest(Contract):
    owner: Literal["accounting"] = "accounting"


class RunRequest(Contract):
    code: Literal[
        "SOURCE_RECONCILIATION",
        "ACCOUNT_LEDGER",
        "DAY_BOOK",
        "TRIAL_BALANCE",
        "PROFIT_LOSS",
        "INCOME_EXPENSE",
        "BALANCE_SHEET",
        "BALANCE_CONTINUITY",
        "ACCOUNT_SUMMARY",
        "PARTY_LEDGER",
        "OUTSTANDING_BILLS",
        "ADVANCES",
        "AGING",
        "CASH_BOOK",
        "BANK_BOOK",
        "BANK_RECONCILIATION",
        "BANK_RECONCILIATION_EVIDENCE",
        "BANK_RECONCILIATION_WORKLIST",
        "PAYMENT_REGISTER",
        "RECEIPT_REGISTER",
        "SALES_REGISTER",
        "PURCHASE_REGISTER",
        "INVOICE_COMPONENT_REGISTER",
        "INVOICE_TAX_REGISTER",
        "INVOICE_CREDIT_REGISTER",
        "INVOICE_SETTLEMENT_REGISTER",
        "INVOICE_GL_BRIDGE",
        "TAX_GL_BRIDGE",
    ] = "SOURCE_RECONCILIATION"
    generation_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    search: str = Field(default="", max_length=200)
    tax_code: str | None = Field(default=None, min_length=1, max_length=64)
    tax_ledger_id: uuid.UUID | None = None
    tax_purpose: str | None = Field(default=None, min_length=1, max_length=64)
    journal_id: uuid.UUID | None = None
    date_basis: Literal["POSTING", "DOCUMENT", "TAX_POINT"] = "POSTING"
    company_registration_id: uuid.UUID | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    account_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None
    basis: Literal["BASE", "TRANSACTION"] = "BASE"
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    grain: Literal["DAY", "MONTH"] = "DAY"
    comparative_from: dt.date | None = None
    comparative_to: dt.date | None = None
    show_zero: bool = False
    statement_balance: str | None = Field(default=None, pattern=r"^-?\d{1,15}(\.\d{1,4})?$")

    @model_validator(mode="after")
    def bounded_report(self) -> Self:
        if (self.tax_ledger_id or self.tax_purpose) and self.code != "TAX_GL_BRIDGE":
            raise ValueError("tax ledger and purpose filters require the tax bridge")
        if (self.search or self.tax_code) and self.code not in {
            "INVOICE_TAX_REGISTER",
            "INVOICE_CREDIT_REGISTER",
            "TAX_GL_BRIDGE",
        }:
            raise ValueError("tax search and code filters require a tax report")
        if self.journal_id and self.code not in {
            "ACCOUNT_LEDGER",
            "DAY_BOOK",
            "PARTY_LEDGER",
            "CASH_BOOK",
            "BANK_BOOK",
        }:
            raise ValueError("journal filtering requires a ledger")
        invoice_codes = {
            "SALES_REGISTER",
            "PURCHASE_REGISTER",
            "INVOICE_COMPONENT_REGISTER",
            "INVOICE_TAX_REGISTER",
            "INVOICE_CREDIT_REGISTER",
            "INVOICE_SETTLEMENT_REGISTER",
            "INVOICE_GL_BRIDGE",
            "TAX_GL_BRIDGE",
        }
        if self.code not in invoice_codes and (
            self.invoice_id or self.company_registration_id or self.date_basis != "POSTING"
        ):
            raise ValueError("invoice filters require an invoice register")
        if self.date_basis == "DOCUMENT" and self.code not in {
            "SALES_REGISTER",
            "PURCHASE_REGISTER",
            "INVOICE_TAX_REGISTER",
        }:
            raise ValueError("document-date selection is unavailable for this report")
        if self.date_basis == "TAX_POINT" and self.code not in {
            "INVOICE_TAX_REGISTER",
            "TAX_GL_BRIDGE",
        }:
            raise ValueError("tax-date selection requires a tax register or tax bridge")
        if self.company_registration_id and self.code not in {
            "INVOICE_TAX_REGISTER",
            "INVOICE_CREDIT_REGISTER",
            "TAX_GL_BRIDGE",
        }:
            raise ValueError("registration filtering requires a tax component grain")
        if self.code == "SOURCE_RECONCILIATION" and (
            any(
                (
                    self.date_from,
                    self.date_to,
                    self.account_id,
                    self.session_id,
                    self.group_id,
                    self.party_id,
                    self.role,
                    self.currency,
                    self.comparative_from,
                    self.comparative_to,
                    self.statement_balance,
                )
            )
            or self.basis != "BASE"
            or self.grain != "DAY"
        ):
            raise ValueError("source reconciliation covers the complete source snapshot")
        if self.basis == "BASE" and self.currency is not None:
            raise ValueError("base currency is determined by the company snapshot")
        if self.code != "SOURCE_RECONCILIATION":
            if self.date_from is None or self.date_to is None or self.date_from > self.date_to:
                raise ValueError("a valid report date range is required")
        if (self.comparative_from is None) != (self.comparative_to is None):
            raise ValueError("both comparative dates are required")
        if (
            self.comparative_from
            and self.comparative_to
            and self.comparative_from > self.comparative_to
        ):
            raise ValueError("invalid comparative date range")
        statements = {"TRIAL_BALANCE", "PROFIT_LOSS", "INCOME_EXPENSE", "BALANCE_SHEET"}
        if self.code == "BALANCE_CONTINUITY" and (
            self.basis != "BASE"
            or self.grain != "DAY"
            or any(
                (
                    self.account_id,
                    self.group_id,
                    self.party_id,
                    self.role,
                    self.comparative_from,
                    self.comparative_to,
                )
            )
        ):
            raise ValueError(
                "continuity requires complete-company base-currency inputs without comparison"
            )
        if self.code in statements and (
            self.basis != "BASE" or any((self.account_id, self.group_id, self.party_id, self.role))
        ):
            raise ValueError("financial statements require complete-company base-currency inputs")
        if self.basis == "TRANSACTION" and self.currency is None:
            raise ValueError("transaction basis requires one selected currency")
        if self.code == "BANK_RECONCILIATION" and (
            self.account_id is None or self.statement_balance is None
        ):
            raise ValueError(
                "bank reconciliation requires a bank account and statement closing balance"
            )
        if self.code == "BANK_RECONCILIATION_EVIDENCE" and (
            self.account_id is None or self.session_id is None
        ):
            raise ValueError("evidence-backed bank reconciliation requires an account and session")
        if self.code == "BANK_RECONCILIATION_EVIDENCE" and (
            self.basis != "TRANSACTION" or self.comparative_from is not None
        ):
            raise ValueError("bank session evidence needs account currency without comparison")
        if self.code == "BANK_RECONCILIATION_WORKLIST" and (
            self.account_id is None
            or self.basis != "TRANSACTION"
            or self.comparative_from is not None
            or self.group_id is not None
            or self.party_id is not None
            or self.role is not None
        ):
            raise ValueError("bank worklist needs one bank account and its transaction currency")
        if self.code != "BANK_RECONCILIATION_EVIDENCE" and self.session_id is not None:
            raise ValueError("session selection requires evidence-backed bank reconciliation")
        if self.code == "BANK_RECONCILIATION" and any((self.group_id, self.party_id, self.role)):
            raise ValueError("bank reconciliation requires the complete selected bank ledger")
        if self.statement_balance is not None and not Decimal(self.statement_balance).is_finite():
            raise ValueError("statement balance must be finite")
        if self.code == "BANK_RECONCILIATION" and self.comparative_from:
            raise ValueError("create a separate bank reconciliation with its own statement balance")
        if self.code != "BANK_RECONCILIATION" and self.statement_balance is not None:
            raise ValueError("statement balance is only available for bank reconciliation")
        return self


class GenerationDetail(Contract):
    id: uuid.UUID
    status: str
    applied_sequence: int
    target_sequence: int | None
    failure_code: str | None
    manifest: dict[str, Any] | None


class RunDetail(Contract):
    id: uuid.UUID
    generation_id: uuid.UUID
    status: str
    evidence: dict[str, Any] | None
    failure_code: str | None
    download_token: str | None = None


class RowItem(Contract):
    id: uuid.UUID
    ordinal: int
    data: dict[str, Any]


class RowPage(Contract):
    items: list[RowItem]
    page: PageMeta


class ListQuery(Contract):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=4096)


class Definition(Contract):
    code: str
    version: int
    rule_hash: str
    formats: tuple[Literal["CSV"], ...] = ("CSV",)
    financial_statement: bool = False


class ListItem(Contract):
    id: uuid.UUID
    status: str
    generation_id: uuid.UUID | None = None
    applied_sequence: int | None = None


class ResourcePage(Contract):
    items: list[ListItem]
    page: PageMeta
