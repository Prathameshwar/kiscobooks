"""Opening reconciliation and debtor/creditor posting integration."""

import uuid
from decimal import Decimal
from typing import Any, cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.subledger import Allocation, OpeningBatch, OpenItem, SourceDocument
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import create_journal, journal_setup, ledger_headers, post_journal
from tests.test_masters import new_party, post


def multi_currency_headers() -> dict[str, str]:
    """Fresh headers (so a fresh idempotency key) for every command."""
    return ledger_headers(features={"multi_currency"})


async def party_accounts(
    client: httpx.AsyncClient, *, currency: str = "INR"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """One party with its customer and supplier ledger accounts.

    A party never exists without its account (docs/party-ledger-mandatory-plan.md), so these are
    the accounts that the customer role (at creation) and the supplier role (at activation) bring
    with them, named and given a currency through the ledger choices, not created separately.
    """
    fixed = currency != "INR"

    def ledger(role: str) -> dict[str, Any]:
        return {
            "code": role,
            "name": role + " account",
            "currency_mode": "FIXED" if fixed else "BASE",
            "currency": currency if fixed else None,
        }

    p = await new_party(
        client, role="CUSTOMER", h=multi_currency_headers(), ledger=ledger("CUSTOMER")
    )
    supplier_role = await post(
        client,
        "/party-roles",
        {"party_id": p["id"], "role": "SUPPLIER"},
        h=multi_currency_headers(),
    )
    await post(
        client,
        f"/party-roles/{supplier_role['id']}/activate",
        {"expected_version": supplier_role["row_version"], "ledger": ledger("SUPPLIER")},
        h=multi_currency_headers(),
        status=200,
    )
    listed = (
        await client.get(BASE + "/accounts?kind=PARTY&limit=200", headers=ledger_headers())
    ).json()["items"]
    result = []
    for code in ("CUSTOMER", "SUPPLIER"):
        listed_row = next(row for row in listed if row["code"] == code)
        detail = await client.get(f"{BASE}/accounts/{listed_row['id']}", headers=ledger_headers())
        assert detail.status_code == 200, detail.text
        result.append(detail.json())
    return p, result[0], result[1]


async def source(
    client: httpx.AsyncClient,
    account: dict[str, Any],
    offset: str,
    *,
    kind: str = "INVOICE",
    amount: str = "100",
    date: str = "2026-04-02",
    currency: str = "INR",
    rate: str = "1",
    **extra: Any,
) -> dict[str, Any]:
    body = {
        "kind": kind,
        "account_id": account["id"],
        "counterpart_account_id": offset,
        "currency": currency,
        "amount": amount,
        "exchange_rate": rate,
        "document_date": date,
        "posting_date": date,
        "reference": "DOC-" + str(uuid.uuid4())[:8],
        "source_system": "billing",
        "source_type": kind.lower(),
        "source_id": str(uuid.uuid4()),
        "description": "Source document",
        **extra,
    }
    response = await client.post(
        BASE + "/source-documents",
        json=body,
        headers=ledger_headers(features={"multi_currency", "credit_limits"}),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


async def post_source(client: httpx.AsyncClient, row: dict[str, Any]) -> httpx.Response:
    journal = (
        await client.get(BASE + f"/journals/{row['journal_id']}", headers=ledger_headers())
    ).json()
    return await post_journal(client, journal, features={"multi_currency", "credit_limits"})


async def test_opening_ties_bills_and_posts_every_effect_once(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    _, customer, _ = await party_accounts(client)
    body["lines"][0]["account_id"] = customer["id"]
    opening = {
        "posting_date": "2026-04-01",
        "description": "Imported balances",
        "lines": body["lines"],
        "bills": [
            {
                "line_sequence": 1,
                "reference": "OLD-1",
                "amount": "70.25",
                "document_date": "2026-03-01",
                "due_date": "2026-03-31",
            },
            {
                "line_sequence": 1,
                "reference": "OLD-2",
                "amount": "30",
                "document_date": "2026-03-15",
                "due_date": "2026-04-15",
            },
        ],
    }
    preview = await client.post(
        BASE + "/opening-batches/preview", json=opening, headers=ledger_headers()
    )
    assert preview.status_code == 200 and preview.json()["bill_count"] == 2, preview.text
    broken = opening | {"bills": opening["bills"][:1]}
    assert (
        await client.post(BASE + "/opening-batches", json=broken, headers=ledger_headers())
    ).status_code == 422
    created = await client.post(
        BASE + "/opening-batches", json=opening, headers=ledger_headers(key="opening-import")
    )
    assert created.status_code == 201, created.text
    duplicate = await client.post(
        BASE + "/opening-batches", json=opening, headers=ledger_headers(key="opening-import")
    )
    assert duplicate.json()["id"] == created.json()["id"]
    assert (
        await client.post(BASE + "/opening-batches", json=opening, headers=ledger_headers())
    ).status_code == 409
    posted = await post_source(client, created.json())
    assert posted.status_code == 200, posted.text
    finalized = (
        await client.get(
            BASE + f"/opening-batches/{created.json()['id']}", headers=ledger_headers()
        )
    ).json()
    assert finalized["status"] == "FINALIZED"
    items = (await client.get(BASE + "/open-items", headers=ledger_headers())).json()["items"]
    assert len(items) == 2 and sum(Decimal(row["amount"]) for row in items) == Decimal("100.25")
    assert (await post_source(client, created.json())).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(OpenItem.id))) == 2
            assert sum(await db.scalars(select(OpenItem.base_amount))) == Decimal("100.25")


async def test_zero_opening_gate_and_source_customer_supplier_terms(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    draft = await create_journal(client, body)
    rejected = await post_journal(client, draft)
    assert rejected.status_code == 409 and "opening" in rejected.text
    batch = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero balances"},
        headers=ledger_headers(),
    )
    assert batch.status_code == 201
    finalized = await client.post(
        BASE + f"/opening-batches/{batch.json()['id']}/finalize-zero",
        json={"expected_version": 1},
        headers=ledger_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    assert (await post_journal(client, draft)).status_code == 200
    _, customer, supplier = await party_accounts(client)
    for account, kind, direction in (
        (customer, "INVOICE", "DEBT"),
        (supplier, "BILL", "DEBT"),
        (customer, "RECEIPT", "CREDIT"),
        (supplier, "PAYMENT", "CREDIT"),
    ):
        item = await source(
            client,
            account,
            body["lines"][0 if kind in {"RECEIPT", "PAYMENT"} else 1]["account_id"],
            kind=kind,
        )
        assert (await post_source(client, item)).status_code == 200
        assert item["direction"] == direction
    rows = (await client.get(BASE + "/open-items?limit=20", headers=ledger_headers())).json()[
        "items"
    ]
    assert len(rows) == 4
    debts = [row for row in rows if row["direction"] == "DEBT"]
    assert all(row["due_date"] == "2026-05-02" for row in debts)
    assert {row["role"] for row in rows} == {"CUSTOMER", "SUPPLIER"}


async def test_opening_reversal_replacement_and_source_replay_drift(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    opening = await client.post(
        BASE + "/opening-batches",
        json={
            "posting_date": "2026-04-01",
            "description": "Opening correction",
            "lines": body["lines"],
        },
        headers=ledger_headers(),
    )
    assert opening.status_code == 201
    assert (await post_source(client, opening.json())).status_code == 200
    reverse = await client.post(
        BASE + f"/journals/{opening.json()['journal_id']}/reversal",
        json={"posting_date": "2026-04-01", "reason": "Correct opening"},
        headers=ledger_headers(),
    )
    assert reverse.status_code == 201, reverse.text
    assert (await post_journal(client, reverse.json())).status_code == 200
    replacement = await client.post(
        BASE + "/opening-batches",
        json={
            "posting_date": "2026-04-01",
            "description": "Correct zero opening",
            "replacement_of_id": opening.json()["id"],
        },
        headers=ledger_headers(),
    )
    assert replacement.status_code == 201, replacement.text
    assert (
        await client.post(
            BASE + f"/opening-batches/{replacement.json()['id']}/finalize-zero",
            json={"expected_version": 1},
            headers=ledger_headers(),
        )
    ).status_code == 200
    _, customer, _ = await party_accounts(client)
    row = await source(client, customer, body["lines"][1]["account_id"])
    replay = await client.post(
        BASE + "/source-documents", json=row["payload"]["request"], headers=ledger_headers()
    )
    assert replay.status_code == 201 and replay.json()["id"] == row["id"], replay.text
    conflict = await client.post(
        BASE + "/source-documents",
        json=row["payload"]["request"] | {"due_date": "2026-06-01"},
        headers=ledger_headers(),
    )
    assert conflict.status_code == 409, conflict.text


async def test_opening_auth_scope_validation_and_tenant_filter(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)
    req = {"posting_date": "2026-04-01", "description": "Unauthorized opening"}
    assert (await client.post(BASE + "/opening-batches", json=req)).status_code == 401
    assert (
        await client.post(
            BASE + "/opening-batches", json=req, headers=ledger_headers(permissions=set())
        )
    ).status_code == 403
    assert (
        await client.post(
            BASE + "/opening-batches", json=req | {"unexpected": 1}, headers=ledger_headers()
        )
    ).status_code == 422
    rows = (await client.get(BASE + "/opening-batches", headers=ledger_headers())).json()["items"]
    other_path = BASE.replace(str(COMPANY), str(uuid7())) + "/opening-batches/" + rows[0]["id"]
    company_id = uuid.UUID(other_path.split("/")[3])
    assert (
        await client.get(other_path, headers=ledger_headers(company=company_id))
    ).status_code == 403
    with tenant_scope(uuid7()):
        async with app.state.session_factory() as db:
            for model in (OpeningBatch, SourceDocument, OpenItem, Allocation):
                assert await db.scalar(select(func.count(model.id))) == 0
