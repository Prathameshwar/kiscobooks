"""Versioned native entry contract shared by document capture and the money owner."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal, Self

from billing_platform.exact import exact_decimal, exact_rate
from pydantic import (
    BeforeValidator,
    PlainSerializer,
    Field,
    StrictBool,
    WithJsonSchema,
    field_serializer,
    model_validator,
)

from voucher_execution.contracts import Contract

Amount = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    WithJsonSchema({"type": "string"}, mode="validation"),
    Field(gt=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
    PlainSerializer(lambda value: format(value, ".4f"), return_type=str, when_used="json"),
]
Rate = Annotated[
    Decimal,
    BeforeValidator(exact_rate),
    WithJsonSchema({"type": "string"}, mode="validation"),
    Field(gt=0, max_digits=19, decimal_places=8, allow_inf_nan=False),
    PlainSerializer(lambda value: format(value, ".8f"), return_type=str, when_used="json"),
]
Mode = Literal["CASH", "CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"]


class AccountEntry(Contract):
    line_key: uuid.UUID
    account_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1)
    side: Literal["DEBIT", "CREDIT"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount
    exchange_rate: Rate = Decimal("1")
    purpose: Literal["PRINCIPAL", "DISCOUNT", "FEE", "ROUNDING"] = "PRINCIPAL"
    description: str = Field(default="", max_length=500)
    tracking: Literal["NONE", "NEW_REF", "ON_ACCOUNT", "ADVANCE"] = "NONE"
    bill_reference: str | None = Field(default=None, min_length=1, max_length=120)
    due_date: dt.date | None = None

    @model_validator(mode="after")
    def tracking_fields(self) -> Self:
        if self.tracking == "NONE" and (self.bill_reference or self.due_date):
            raise ValueError("bill fields require explicit tracking")
        # A new bill names its reference; without a due date it is due on the document date.
        if self.tracking == "NEW_REF" and not self.bill_reference:
            raise ValueError("new reference requires a reference")
        return self


class Tender(Contract):
    tender_key: uuid.UUID
    line_key: uuid.UUID
    mode: Mode
    amount: Amount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reference: str | None = Field(default=None, min_length=1, max_length=120)
    instrument_date: dt.date | None = None
    recognition: Literal["BOOK_DATE", "MATURITY_DATE"] = "BOOK_DATE"

    @model_validator(mode="after")
    def evidence(self) -> Self:
        # A non-cash reference (UTR, cheque or card slip number) is recorded when given and
        # never demanded: bank reconciliation matches on account, date and amount as well.
        if self.mode == "CASH":
            if self.reference or self.instrument_date or self.recognition != "BOOK_DATE":
                raise ValueError("cash has no banking instrument")
        if self.mode == "CHEQUE" and self.instrument_date is None:
            raise ValueError("cheque date is required")
        if self.recognition == "MATURITY_DATE" and self.mode != "CHEQUE":
            raise ValueError("maturity recognition is supported only for cheques")
        return self


class BillTarget(Contract):
    item_id: uuid.UUID | None = None
    line_key: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if (self.item_id is None) == (self.line_key is None):
            raise ValueError("select an existing item or a new entry, exclusively")
        return self


class BillAllocation(Contract):
    allocation_key: uuid.UUID
    debt: BillTarget
    credit: BillTarget
    amount: Amount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    fx_account_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def different_targets(self) -> Self:
        if self.debt == self.credit:
            raise ValueError("allocation requires different debt and credit targets")
        return self


class MoneyInput(Contract):
    schema_version: Literal[1] = 1
    purpose: Literal[
        "GENERAL", "TRANSFER", "SETTLEMENT", "ADVANCE", "REFUND", "BILL_ADJUSTMENT"
    ] = "GENERAL"
    accounts: tuple[AccountEntry, ...] = Field(default=(), max_length=200)
    tenders: tuple[Tender, ...] = Field(default=(), max_length=200)
    allocations: tuple[BillAllocation, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def structural_integrity(self) -> Self:
        for values, key in (
            (self.accounts, "line_key"),
            (self.tenders, "tender_key"),
            (self.allocations, "allocation_key"),
        ):
            if len({getattr(value, key) for value in values}) != len(values):
                raise ValueError("duplicate financial detail identity")
        entries = {entry.line_key: entry for entry in self.accounts}
        if self.purpose == "BILL_ADJUSTMENT":
            if self.accounts or self.tenders or not self.allocations:
                raise ValueError("pure bill adjustment contains allocations only")
        elif len(self.accounts) < 2:
            raise ValueError("money posting requires at least two account entries")
        for allocation in self.allocations:
            for target in (allocation.debt, allocation.credit):
                if target.line_key and (
                    target.line_key not in entries or entries[target.line_key].tracking == "NONE"
                ):
                    raise ValueError("allocation target requires a tracked entry")
        for tender in self.tenders:
            entry = entries.get(tender.line_key)
            if entry is None or entry.currency != tender.currency:
                raise ValueError("tender must match a same-currency account entry")
        for line_key in {t.line_key for t in self.tenders}:
            if (
                sum(
                    (t.amount for t in self.tenders if t.line_key == line_key),
                    Decimal(0),
                )
                != entries[line_key].amount
            ):
                raise ValueError("split tenders must exactly cover their account entry")
        return self


class MoneyPolicy(Contract):
    """Controls can narrow compiled capabilities; dimensions and tax are later contracts."""

    allowed_account_kinds: frozenset[Literal["GENERAL", "CASH", "BANK", "PARTY"]] = frozenset(
        {"GENERAL", "CASH", "BANK", "PARTY"}
    )
    allowed_payment_modes: frozenset[Mode] = frozenset(
        {"CASH", "CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"}
    )
    allowed_tracking: frozenset[Literal["NONE", "NEW_REF", "ON_ACCOUNT", "ADVANCE"]] = frozenset(
        {"NONE", "NEW_REF", "ON_ACCOUNT", "ADVANCE"}
    )
    allowed_recognition: frozenset[Literal["BOOK_DATE", "MATURITY_DATE"]] = frozenset(
        {"BOOK_DATE", "MATURITY_DATE"}
    )
    allowed_account_ids: frozenset[uuid.UUID] | None = Field(default=None, max_length=500)
    split_tenders_allowed: StrictBool = True
    allocations_allowed: StrictBool = True
    settlement_adjustments_allowed: StrictBool = False
    journal_cash_bank_allowed: StrictBool = False
    foreign_currency_allowed: StrictBool = False
    max_account_entries: int = Field(default=200, strict=True, ge=2, le=200)

    @field_serializer("*", when_used="json")
    def deterministic(self, value: object) -> object:
        return sorted(value) if isinstance(value, frozenset) else value


def restrict_money(parent: MoneyPolicy, child: MoneyPolicy) -> MoneyPolicy:
    result = child.model_dump()
    for key in MoneyPolicy.model_fields:
        left, right = getattr(parent, key), getattr(child, key)
        if key == "allowed_account_ids":
            result[key] = (
                left & right
                if left is not None and right is not None
                else left
                if left is not None
                else right
            )
        elif isinstance(left, frozenset):
            result[key] = left & right
        elif isinstance(left, bool):
            result[key] = left and right
        else:
            result[key] = min(left, right)
    return MoneyPolicy.model_validate(result)


def validate_entry_controls(
    body: MoneyInput,
    policy: MoneyPolicy,
    *,
    kind: str,
    profile: str,
    posting_date: dt.date | None,
) -> None:
    if kind not in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}:
        raise ValueError("financial entry is not implemented for this kind")
    if profile != "STANDARD" and not (profile == "ADVANCE" and kind in {"PAYMENT", "RECEIPT"}):
        raise ValueError("financial entry is not implemented for this profile")
    if body.purpose == "BILL_ADJUSTMENT" and kind != "JOURNAL":
        raise ValueError("pure bill adjustment uses Journal")
    if kind == "CONTRA" and (
        body.purpose != "TRANSFER"
        or body.allocations
        or any(e.tracking != "NONE" for e in body.accounts)
    ):
        raise ValueError("Contra requires an untracked cash/bank transfer")
    if profile == "ADVANCE" and body.purpose != "ADVANCE":
        raise ValueError("advance profile requires advance purpose")
    validate_money_controls(body, policy, posting_date=posting_date, transfer=kind == "CONTRA")


def validate_money_controls(
    body: MoneyInput, policy: MoneyPolicy, *, posting_date: dt.date | None, transfer: bool = False
) -> None:
    """Common entry/tender controls, also applied to owner-generated invoice distributions."""
    if len(body.accounts) > policy.max_account_entries:
        raise ValueError("too many configured account entries")
    if body.allocations and not policy.allocations_allowed:
        raise ValueError("bill allocations are disabled")
    tender_groups = len({tender.line_key for tender in body.tenders}) if transfer else 1
    if not policy.split_tenders_allowed and len(body.tenders) > tender_groups:
        raise ValueError("split tenders are disabled")
    for entry in body.accounts:
        if (
            policy.allowed_account_ids is not None
            and entry.account_id not in policy.allowed_account_ids
        ):
            raise ValueError("account is excluded by voucher configuration")
        if entry.tracking not in policy.allowed_tracking:
            raise ValueError("bill tracking mode is disabled")
        if entry.purpose != "PRINCIPAL" and not policy.settlement_adjustments_allowed:
            raise ValueError("settlement adjustments are disabled")
    for tender in body.tenders:
        if (
            tender.mode not in policy.allowed_payment_modes
            or tender.recognition not in policy.allowed_recognition
        ):
            raise ValueError("tender mode or recognition is disabled")
        if (
            posting_date
            and tender.recognition == "MATURITY_DATE"
            and tender.instrument_date
            and posting_date < tender.instrument_date
        ):
            raise ValueError("maturity recognition cannot be booked before instrument date")
