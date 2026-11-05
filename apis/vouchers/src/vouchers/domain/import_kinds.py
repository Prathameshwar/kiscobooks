"""Which voucher kinds import, and the family (invoice or money) whose rules each follows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from vouchers.domain import import_money as money
from vouchers.domain import imports as invoices
from vouchers.domain.imports import CustomColumn, Issue, Staged, Template

KINDS = (*invoices.INVOICE_KINDS, *money.MONEY_KINDS)
Family = Literal["INVOICE", "MONEY"]
# Profiles the import supports: standard everywhere, plus advance payments and receipts.
PROFILES = {kind: frozenset({"STANDARD"}) for kind in KINDS} | {
    "PAYMENT": frozenset({"STANDARD", "ADVANCE"}),
    "RECEIPT": frozenset({"STANDARD", "ADVANCE"}),
}
# Only Purchase identifies its document by a number the other party chose on a date.
DUPLICATE_RULES = {"PURCHASE": invoices.DUPLICATE_RULES}


def family(kind: str) -> Family:
    if kind in invoices.INVOICE_KINDS:
        return "INVOICE"
    if kind in money.MONEY_KINDS:
        return "MONEY"
    raise ValueError("voucher kind cannot be imported")


def required(kind: str) -> frozenset[str]:
    return invoices.REQUIRED_NATIVE if family(kind) == "INVOICE" else money.REQUIRED_NATIVE


def template(kind: str, denied: frozenset[str], custom: Iterable[CustomColumn]) -> Template:
    if family(kind) == "INVOICE":
        return invoices.template(denied, custom, kind=kind)
    return money.template(kind, denied, custom)


def parse(kind: str, item: Staged, shape: Template) -> tuple[Any | None, list[Issue]]:
    if family(kind) == "INVOICE":
        return invoices.parse(item, shape, kind)
    return money.parse(item, shape, kind)


def file_identities(kind: str, doc: Any, rule: str) -> list[tuple[tuple[str, ...], str, str]]:
    if family(kind) == "INVOICE":
        return invoices.file_identities(doc, rule)
    return money.file_identities(doc)


def label(kind: str) -> str:
    return kind.replace("_", " ").title()
