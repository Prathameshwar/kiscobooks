"""Ordinary money profiles, independent of SQL and HTTP."""

import datetime as dt
import uuid
from dataclasses import dataclass

from billing_platform.errors import ValidationFailedError
from voucher_execution.money import MoneyInput, MoneyPolicy, validate_entry_controls


@dataclass(frozen=True)
class MoneyAccount:
    id: uuid.UUID
    kind: str
    posting_policy: str
    party_role: str | None
    version: int


def validate_accounts(
    body: MoneyInput,
    policy: MoneyPolicy,
    accounts: dict[uuid.UUID, MoneyAccount],
    *,
    kind: str,
    profile: str,
    base_currency: str,
    posting_date: dt.date,
) -> None:
    try:
        validate_entry_controls(body, policy, kind=kind, profile=profile, posting_date=posting_date)
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    cash_keys = set()
    for entry in body.accounts:
        account = accounts[entry.account_id]
        if account.version != entry.source_version:
            raise ValidationFailedError("selected account version changed")
        if account.kind not in policy.allowed_account_kinds:
            raise ValidationFailedError("account kind is excluded by configuration")
        if entry.currency != base_currency and not policy.foreign_currency_allowed:
            raise ValidationFailedError("foreign currency entries are disabled")
        if account.kind == "PARTY":
            if account.party_role not in {"CUSTOMER", "SUPPLIER"} or entry.tracking == "NONE":
                raise ValidationFailedError(
                    "party entries require an explicit bill, advance or on-account balance"
                )
            if entry.purpose != "PRINCIPAL":
                raise ValidationFailedError("settlement adjustments require a general ledger")
        elif account.posting_policy != "MANUAL_ALLOWED" or entry.tracking != "NONE":
            raise ValidationFailedError(
                "ordinary entries cannot use protected control accounts or non-party bill tracking"
            )
        if account.kind in {"CASH", "BANK"}:
            cash_keys.add(entry.line_key)
            if entry.purpose != "PRINCIPAL":
                raise ValidationFailedError("cash and bank amounts are principal tender entries")
            if kind == "JOURNAL" and not policy.journal_cash_bank_allowed:
                raise ValidationFailedError(
                    "cash/bank journal entries require explicit configuration"
                )
            expected = {"PAYMENT": "CREDIT", "RECEIPT": "DEBIT"}.get(kind)
            if expected and entry.side != expected:
                raise ValidationFailedError("tender direction differs from voucher kind")
        elif kind == "CONTRA":
            raise ValidationFailedError("Contra accepts cash and bank accounts only")
        if body.purpose in {"ADVANCE", "REFUND"} and account.kind == "PARTY":
            expected_role = "SUPPLIER" if kind == "PAYMENT" else "CUSTOMER"
            if body.purpose == "REFUND":
                expected_role = "CUSTOMER" if kind == "PAYMENT" else "SUPPLIER"
            if kind not in {"PAYMENT", "RECEIPT"} or account.party_role != expected_role:
                raise ValidationFailedError("advance or refund party role differs from direction")
            if body.purpose == "ADVANCE" and entry.tracking != "ADVANCE":
                raise ValidationFailedError("advance purpose requires advance tracking")
    if kind in {"PAYMENT", "RECEIPT", "CONTRA"} and not cash_keys:
        raise ValidationFailedError("cash or bank entry is required")
    if kind == "CONTRA" and len({entry.account_id for entry in body.accounts}) < 2:
        raise ValidationFailedError("a transfer requires distinct accounts")
    if body.purpose in {"ADVANCE", "REFUND"} and not any(
        accounts[entry.account_id].kind == "PARTY" for entry in body.accounts
    ):
        raise ValidationFailedError("advance or refund requires a party")
    if {tender.line_key for tender in body.tenders} != cash_keys:
        raise ValidationFailedError("each cash/bank entry requires matching tender evidence")
    by_key = {entry.line_key: entry for entry in body.accounts}
    for tender in body.tenders:
        account = accounts[by_key[tender.line_key].account_id]
        if (tender.mode == "CASH") != (account.kind == "CASH"):
            raise ValidationFailedError("payment mode differs from its cash/bank account")
