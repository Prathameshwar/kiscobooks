import hashlib
import uuid
from collections import Counter

from billing_platform.idempotency import canonical_json
from conftest import COMPANY, TENANT
from reporting_contract.contract import FACT_MODELS, Fact, Manifest, digest


def source(entity, identity, data):
    value = {"entity": entity, "source_id": str(identity), "data": data}
    return Fact.model_validate(value | {"content_hash": digest(value)})


def dataset():
    head, group, account, finance, year, period, journal, line1, line2 = [
        uuid.uuid4() for _ in range(9)
    ]
    pairs = [
        ("account_head", head, {"code": "ASSET", "name": "Assets", "nature": "ASSET"}),
        (
            "account_group",
            group,
            {
                "code": "CASH",
                "name": "Cash",
                "head_id": str(head),
                "parent_id": None,
                "status": "ACTIVE",
                "system_key": None,
                "is_deemed_positive": False,
                "affects_gross_profit": False,
                "nett_balances": False,
                "sort_order": 1,
            },
        ),
        (
            "account",
            account,
            {
                "code": "CASH",
                "name": "Cash",
                "group_id": str(group),
                "kind": "CASH",
                "party_id": None,
                "party_role": None,
                "currency_mode": "BASE",
                "currency": None,
                "status": "ACTIVE",
                "system_key": None,
            },
        ),
        (
            "financial_setup",
            finance,
            {
                "base_currency": "INR",
                "books_begin_date": "2026-04-01",
                "fiscal_year_start_month": 4,
                "fiscal_year_start_day": 1,
                "configuration_hash": "a" * 64,
                "first_posted_at": "2026-04-01T00:00:00Z",
            },
        ),
        (
            "fiscal_year",
            year,
            {"code": "2026", "start_date": "2026-04-01", "end_date": "2027-03-31"},
        ),
        (
            "fiscal_period",
            period,
            {
                "fiscal_year_id": str(year),
                "sequence": 1,
                "code": "2026-04",
                "start_date": "2026-04-01",
                "end_date": "2026-04-30",
                "status": "OPEN",
                "row_version": 1,
            },
        ),
        (
            "journal",
            journal,
            {
                "kind": "MANUAL",
                "description": "Source fixture",
                "status": "POSTED",
                "document_date": "2026-04-01",
                "posting_date": "2026-04-01",
                "base_currency": "INR",
                "total_debit": "100.0000",
                "total_credit": "100.0000",
                "source_system": "accounting",
                "source_type": "journal",
                "source_id": str(journal),
                "source_hash": "b" * 64,
                "number": "J/1",
                "fiscal_period_id": str(period),
                "reversal_of_id": None,
                "configuration_hash": "a" * 64,
                "posted_at": "2026-04-01T00:00:00Z",
            },
        ),
    ]
    for identity, side in ((line1, "DEBIT"), (line2, "CREDIT")):
        pairs.append(
            (
                "journal_line",
                identity,
                {
                    "journal_id": str(journal),
                    "sequence": 1 if side == "DEBIT" else 2,
                    "account_id": str(account),
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
        )
    return sorted(
        [source(*pair) for pair in pairs], key=lambda row: (row.entity, str(row.source_id))
    )


def manifest(items, *, identity=None, sequence=1, kind="SNAPSHOT", full=None):
    checksum = hashlib.sha256()
    for item in items:
        checksum.update(canonical_json(item.model_dump(mode="json")) + b"\n")
    counts = Counter(
        row.entity for row in (full if full is not None else items) if row.data is not None
    )
    return Manifest.model_validate(
        {
            "id": identity or uuid.uuid4(),
            "tenant_id": TENANT,
            "company_id": COMPANY,
            "kind": kind,
            "sequence": sequence,
            "generation": sequence + 1,
            "scope_hash": "c" * 64,
            "permission_hash": "c" * 64,
            "fact_count": len(items),
            "facts_hash": checksum.hexdigest(),
            "control": {
                "counts": {key: counts[key] for key in FACT_MODELS},
                "base_totals": {"INR": {"DEBIT": "100.0000", "CREDIT": "100.0000"}},
                "coverage_start": "2026-04-01",
                "coverage_kind": "RETAINED_LEDGER",
            },
        }
    )


def settlement_dataset():
    rows = dataset()
    party = uuid.uuid4()
    rows.append(
        source(
            "party",
            party,
            {"code": "BUYER", "name": "Buyer", "party_type": "ORGANISATION", "status": "ACTIVE"},
        )
    )
    journal = next(row for row in rows if row.entity == "journal")
    account = next(row for row in rows if row.entity == "account")
    rows = [
        source(
            row.entity,
            row.source_id,
            row.data
            | {
                "party_id": str(party),
                **(
                    {"party_role": "CUSTOMER", "kind": "PARTY"}
                    if row.entity == "account"
                    else {"role": "CUSTOMER"}
                ),
            },
        )
        if row.entity in {"account", "journal_line"}
        else row
        for row in rows
    ]
    items = []
    for index, line in enumerate(row for row in rows if row.entity == "journal_line"):
        identity = uuid.uuid4()
        items.append(identity)
        rows.append(
            source(
                "open_item",
                identity,
                {
                    "journal_line_id": str(line.source_id),
                    "sequence": 1,
                    "account_id": str(account.source_id),
                    "party_id": str(party),
                    "role": "CUSTOMER",
                    "direction": "DEBT" if index == 0 else "CREDIT",
                    "reference": "INV-1",
                    "currency": "INR",
                    "amount": "100.0000",
                    "base_currency": "INR",
                    "base_amount": "100.0000",
                    "document_date": "2026-04-01",
                    "posting_date": "2026-04-01",
                    "due_date": "2026-04-30",
                    "terms": {},
                    "reversal_journal_id": None,
                    "reversal_date": None,
                },
            )
        )
    rows.append(
        source(
            "allocation",
            uuid.uuid4(),
            {
                "debt_item_id": str(items[0]),
                "credit_item_id": str(items[1]),
                "posting_date": "2026-04-02",
                "currency": "INR",
                "amount": "100.0000",
                "base_currency": "INR",
                "debt_base_amount": "100.0000",
                "credit_base_amount": "100.0000",
                "fx_journal_id": None,
                "reversal_date": None,
                "fx_reversal_id": None,
            },
        )
    )
    rows.append(
        source(
            "opening_batch",
            uuid.uuid4(),
            {
                "status": "FINALIZED",
                "posting_date": "2026-04-01",
                "journal_id": str(journal.source_id),
                "replacement_of_id": None,
                "finalized_at": "2026-04-01T00:00:00Z",
            },
        )
    )
    rows.append(
        source(
            "source_document",
            uuid.uuid4(),
            {
                "journal_id": str(journal.source_id),
                "account_id": str(account.source_id),
                "party_id": str(party),
                "role": "CUSTOMER",
                "status": "POSTED",
                "kind": "INVOICE",
                "direction": "DEBT",
                "currency": "INR",
                "amount": "100.0000",
                "posting_date": "2026-04-01",
                "reference": "INV-1",
            },
        )
    )
    return rows
