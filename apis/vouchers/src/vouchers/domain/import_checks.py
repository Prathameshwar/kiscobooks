"""Duplicate and over-consumption probes for imported vouchers; pure, JSON-serialisable.

Each kind derives probes from what identifies its document in the real world:

- ``bill``: the supplier's bill number and date (+ supplier or ledger) — Purchase.
- ``bill_year``: the supplier's number again in the same financial year on another date — a
  likely mistyped date (GST numbers are unique per supplier and year). Warning only.
- ``external``: a source-system or return reference that identifies the document — Sales
  (any customer) and Credit/Debit Notes (per party).
- ``instrument``: a bank instrument on our bank ledger — a cheque leaf we issued is used once;
  a received cheque is drawer-specific, so it also needs its date and amount; an electronic
  transfer reference (UTR) is unique per bank account.
- ``signature``: no external identity, so only the same date, ledgers, sides and amounts —
  cash money vouchers, journals and Sales without a source reference. Warning only.
- ``entitlement`` / ``allocation``: amounts consuming a limited balance — a note's return
  against an original supply line, or a payment/receipt against an open bill. Rejected when
  the job plus existing unposted drafts would exceed what the owner reports as remaining.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Any, Literal

Severity = Literal["error", "warning"]
IDENTITY = frozenset({"bill", "bill_year", "external", "instrument", "signature"})
CONSUMPTION = frozenset({"entitlement", "allocation"})
MESSAGES = {
    "bill": ("duplicate_supplier_invoice", "a voucher with this bill number and date exists"),
    "bill_year": (
        "possible_duplicate_bill",
        "the supplier already used this bill number in the financial year on another date",
    ),
    "external": ("duplicate_reference", "a voucher with this reference already exists"),
    "instrument": ("duplicate_instrument", "this bank instrument is already recorded"),
    "signature": ("possible_duplicate", "a voucher with the same date, ledgers and amounts exists"),
    "entitlement": (
        "exceeds_original",
        "the return exceeds what remains on the original invoice line",
    ),
    "allocation": ("exceeds_outstanding", "the allocation exceeds the bill's outstanding amount"),
}
COLUMNS = {
    "bill": "supplier_invoice_number",
    "bill_year": "supplier_invoice_date",
    "external": None,
    "instrument": "tender_reference",
    "signature": None,
    "entitlement": "amount",
    "allocation": "against_bill",
}


def probe(name: str, severity: Severity, **facts: Any) -> dict[str, Any]:
    if name not in IDENTITY | CONSUMPTION:
        raise ValueError("unsupported probe")
    return {"probe": name, "severity": severity} | {
        key: str(value) if isinstance(value, Decimal) else value for key, value in facts.items()
    }


def identity(item: dict[str, Any]) -> str:
    """Stable comparison key, excluding presentation and balance-check evidence."""
    ignored = {"severity", "amount", "remaining", "owner_remaining", "checked_at", "column"}
    return json.dumps({k: v for k, v in item.items() if k not in ignored}, sort_keys=True)


def message(item: dict[str, Any]) -> tuple[str, str]:
    return MESSAGES[item["probe"]]


def column(item: dict[str, Any]) -> str | None:
    return item.get("column") or COLUMNS[item["probe"]]


def signature(entries: Iterable[tuple[str, str, Decimal]]) -> list[list[str]]:
    """Order-free ledger/side/amount multiset used by ``signature`` probes."""
    return sorted(
        # Stored amounts carry four decimals; file amounts may not.
        [account, side, format(Decimal(amount).quantize(Decimal("0.0001")), "f")]
        for account, side, amount in entries
    )


def within(
    rows: Iterable[tuple[str, list[dict[str, Any]]]],
) -> dict[str, list[tuple[dict[str, Any], str]]]:
    """Collisions inside one job, in file order.

    Returns, per later import key, each probe it collides on and the earlier key it repeats
    (identity probes), or the probe whose cumulative consumption exceeds the remaining amount
    (consumption probes, attributed to the row that crosses the limit).
    """
    seen: dict[str, str] = {}
    used: dict[str, Decimal] = {}
    found: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for key, probes in rows:
        for item in probes:
            name = identity(item)
            if item["probe"] in IDENTITY:
                if name in seen:
                    found.setdefault(key, []).append((item, seen[name]))
                else:
                    seen[name] = key
                continue
            total = used.get(name, Decimal(0)) + Decimal(item["amount"])
            used[name] = total
            if total > Decimal(item["remaining"]):
                found.setdefault(key, []).append((item, ""))
    return found
