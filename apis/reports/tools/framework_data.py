"""Deterministic, streaming balanced source fixture for reporting benchmarks.

One business transaction contributes one journal and two journal lines. Generated
identities and values are synthetic; no production/user data is read.
"""

import calendar
import datetime as dt
import hashlib
import uuid
from collections import Counter
from collections.abc import Iterator
from typing import Any

from billing_platform.idempotency import canonical_json
from reporting_contract.contract import FACT_MODELS, Fact, Manifest, digest

BEGIN = dt.date(2025, 4, 1)
END = dt.date(2027, 3, 31)


def identity(kind: int, sequence: int = 0) -> uuid.UUID:
    """Stable UUIDv7-shaped fixture IDs with disjoint entity ranges."""
    return uuid.UUID(
        int=(1_743_465_600_000 << 80) | (7 << 76) | (2 << 62) | (kind << 40) | sequence
    )


def source(entity: str, key: uuid.UUID, data: dict[str, Any]) -> Fact:
    value = {"entity": entity, "source_id": str(key), "data": data}
    return Fact.model_validate(value | {"content_hash": digest(value)})


def posting_date(index: int) -> dt.date:
    return BEGIN + dt.timedelta(days=index % ((END - BEGIN).days + 1))


def period_number(date: dt.date) -> int:
    return (date.year - BEGIN.year) * 12 + date.month - BEGIN.month


def facts(transactions: int) -> Iterator[Fact]:
    if transactions < 1 or transactions > 10_000_000:
        raise ValueError("fixture transactions must be between 1 and 10000000")
    for number, (name, kind) in enumerate((("Cash", "CASH"), ("Revenue", "GENERAL"))):
        yield source(
            "account",
            identity(1, number),
            {
                "code": name.upper(),
                "name": name,
                "group_id": str(identity(2, number)),
                "kind": kind,
                "party_id": None,
                "party_role": None,
                "currency_mode": "BASE",
                "currency": None,
                "status": "ACTIVE",
                "system_key": None,
            },
        )
    for number, name in enumerate(("Cash", "Revenue")):
        yield source(
            "account_group",
            identity(2, number),
            {
                "code": name.upper(),
                "name": name,
                "head_id": str(identity(3, number)),
                "parent_id": None,
                "status": "ACTIVE",
                "system_key": None,
                "is_deemed_positive": number == 0,
                "affects_gross_profit": number == 1,
                "nett_balances": False,
                "sort_order": number,
            },
        )
    for number, nature in enumerate(("ASSET", "INCOME")):
        yield source(
            "account_head",
            identity(3, number),
            {
                "code": nature,
                "name": nature.title(),
                "nature": nature,
            },
        )
    yield source(
        "financial_setup",
        identity(4),
        {
            "base_currency": "INR",
            "books_begin_date": BEGIN.isoformat(),
            "fiscal_year_start_month": 4,
            "fiscal_year_start_day": 1,
            "configuration_hash": "a" * 64,
            "first_posted_at": "2025-04-01T00:00:00Z",
        },
    )
    for number in range(24):
        year, month = divmod(BEGIN.month - 1 + number, 12)
        year += BEGIN.year
        month += 1
        yield source(
            "fiscal_period",
            identity(5, number),
            {
                "fiscal_year_id": str(identity(6, number // 12)),
                "sequence": number % 12 + 1,
                "code": f"{year}-{month:02}",
                "start_date": dt.date(year, month, 1).isoformat(),
                "end_date": dt.date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
                "status": "OPEN",
                "row_version": 1,
            },
        )
    for number in range(2):
        yield source(
            "fiscal_year",
            identity(6, number),
            {
                "code": str(BEGIN.year + number),
                "start_date": dt.date(BEGIN.year + number, 4, 1).isoformat(),
                "end_date": dt.date(BEGIN.year + number + 1, 3, 31).isoformat(),
            },
        )
    for number in range(transactions):
        date = posting_date(number)
        key = identity(7, number)
        yield source(
            "journal",
            key,
            {
                "kind": "MANUAL",
                "description": f"Benchmark transaction {number}",
                "status": "POSTED",
                "document_date": date.isoformat(),
                "posting_date": date.isoformat(),
                "base_currency": "INR",
                "total_debit": "100.0000",
                "total_credit": "100.0000",
                "source_system": "accounting",
                "source_type": "journal",
                "source_id": str(key),
                "source_hash": "b" * 64,
                "number": f"BENCH/{number:010}",
                "fiscal_period_id": str(identity(5, period_number(date))),
                "reversal_of_id": None,
                "configuration_hash": "a" * 64,
                "posted_at": date.isoformat() + "T00:00:00Z",
            },
        )
    for number in range(transactions):
        for sequence, side in enumerate(("DEBIT", "CREDIT")):
            yield source(
                "journal_line",
                identity(8, number * 2 + sequence),
                {
                    "journal_id": str(identity(7, number)),
                    "sequence": sequence + 1,
                    "account_id": str(identity(1, sequence)),
                    "side": side,
                    "currency": "INR",
                    "amount": "100.0000",
                    "exchange_rate": "1.00000000",
                    "base_currency": "INR",
                    "base_amount": "100.0000",
                    "party_id": None,
                    "role": None,
                    "component": "PRINCIPAL",
                },
            )


def manifest(
    transactions: int, *, tenant: uuid.UUID, company: uuid.UUID, snapshot: uuid.UUID
) -> Manifest:
    checksum = hashlib.sha256()
    counts: Counter[str] = Counter()
    for item in facts(transactions):
        counts[item.entity] += 1
        checksum.update(canonical_json(item.model_dump(mode="json")) + b"\n")
    total = f"{100 * transactions}.0000"
    return Manifest.model_validate(
        {
            "id": snapshot,
            "tenant_id": tenant,
            "company_id": company,
            "kind": "SNAPSHOT",
            "sequence": 1,
            "generation": 1,
            "scope_hash": "c" * 64,
            "permission_hash": "c" * 64,
            "fact_count": sum(counts.values()),
            "facts_hash": checksum.hexdigest(),
            "control": {
                "counts": {key: counts[key] for key in FACT_MODELS},
                "base_totals": {"INR": {"DEBIT": total, "CREDIT": total}},
                "coverage_start": BEGIN,
                "coverage_kind": "RETAINED_LEDGER",
            },
        }
    )
