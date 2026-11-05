"""Settlement, ageing, currency separation, realized FX and reversal evidence."""

from decimal import Decimal
from typing import Any

import httpx
from fastapi import FastAPI

from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_openings_sources import party_accounts, post_source, source


async def items(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(BASE + "/open-items?limit=200", headers=ledger_headers())
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


async def allocate(
    client: httpx.AsyncClient,
    debt: dict[str, Any],
    credit: dict[str, Any],
    amount: str,
    date: str,
    **extra: Any,
) -> httpx.Response:
    return await client.post(
        BASE + "/allocations",
        json={
            "debt_item_id": debt["id"],
            "credit_item_id": credit["id"],
            "amount": amount,
            "posting_date": date,
            **extra,
        },
        headers=ledger_headers(features={"multi_currency", "credit_limits"}),
    )


async def test_partial_payment_ageing_advance_and_reversal(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    party, customer, supplier = await party_accounts(client)
    invoice = await source(client, customer, body["lines"][1]["account_id"], due_date="2026-04-02")
    receipt = await source(
        client,
        customer,
        body["lines"][0]["account_id"],
        kind="RECEIPT",
        amount="120",
        date="2026-04-05",
    )
    for row in (invoice, receipt):
        assert (await post_source(client, row)).status_code == 200
    rows = await items(client)
    debt, credit = sorted(rows, key=lambda row: row["direction"], reverse=True)
    result = await allocate(client, debt, credit, "40", "2026-04-05")
    assert result.status_code == 201, result.text
    assert (await allocate(client, debt, credit, "70", "2026-04-05")).status_code == 422
    query = {"as_of": "2026-04-10", "party_id": party["id"], "role": "CUSTOMER", "currency": "INR"}
    aged = await client.get(BASE + "/subledger/ageing", params=query, headers=ledger_headers())
    assert aged.status_code == 200, aged.text
    assert (
        Decimal(aged.json()["days_1_30"]) == 60 and Decimal(aged.json()["unapplied_credit"]) == 80
    )
    historical = await client.get(
        BASE + "/subledger/ageing", params=query | {"as_of": "2026-04-03"}, headers=ledger_headers()
    )
    assert (
        Decimal(historical.json()["debt"]) == 100
        and Decimal(historical.json()["unapplied_credit"]) == 0
    )
    blocked = await client.post(
        BASE + f"/journals/{receipt['journal_id']}/reversal",
        json={"posting_date": "2026-04-06", "reason": "Cannot reverse allocated receipt"},
        headers=ledger_headers(),
    )
    assert blocked.status_code == 409
    reversed_allocation = await client.post(
        BASE + f"/allocations/{result.json()['id']}/reverse",
        json={
            "expected_version": result.json()["row_version"],
            "posting_date": "2026-04-06",
            "reason": "Wrong invoice selected",
        },
        headers=ledger_headers(),
    )
    assert reversed_allocation.status_code == 200, reversed_allocation.text
    current = await client.get(BASE + "/subledger/ageing", params=query, headers=ledger_headers())
    assert (
        Decimal(current.json()["debt"]) == 100
        and Decimal(current.json()["unapplied_credit"]) == 120
    )
    before_reverse = await client.get(
        BASE + f"/open-items/{debt['id']}/balance?as_of=2026-04-05", headers=ledger_headers()
    )
    assert Decimal(before_reverse.json()["remaining"]) == 60
    assert (await allocate(client, debt, credit, "10", "2026-04-05")).status_code == 409
    wrong_role = await source(
        client,
        supplier,
        body["lines"][0]["account_id"],
        kind="PAYMENT",
        amount="100",
        date="2026-04-06",
    )
    assert (await post_source(client, wrong_role)).status_code == 200
    supplier_item = next(row for row in await items(client) if row["role"] == "SUPPLIER")
    assert (await allocate(client, debt, supplier_item, "1", "2026-04-06")).status_code == 422


async def test_foreign_settlement_posts_and_reverses_realized_fx_atomically(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client, currency="USD")
    invoice = await source(
        client, customer, body["lines"][1]["account_id"], currency="USD", rate="83"
    )
    receipt = await source(
        client,
        customer,
        body["lines"][0]["account_id"],
        kind="RECEIPT",
        date="2026-04-05",
        currency="USD",
        rate="84",
    )
    for row in (invoice, receipt):
        posted = await post_source(client, row)
        assert posted.status_code == 200, posted.text
    rows = await items(client)
    debt = next(row for row in rows if row["direction"] == "DEBT")
    credit = next(row for row in rows if row["direction"] == "CREDIT")
    assert (await allocate(client, debt, credit, "100", "2026-04-05")).status_code == 422
    result = await allocate(
        client, debt, credit, "100", "2026-04-05", fx_account_id=body["lines"][1]["account_id"]
    )
    assert result.status_code == 201 and result.json()["fx_journal_id"], result.text
    journal = (
        await client.get(
            BASE + f"/journals/{result.json()['fx_journal_id']}", headers=ledger_headers()
        )
    ).json()
    assert (
        journal["kind"] == "REALIZED_FX"
        and journal["authorization_journal_id"] == receipt["journal_id"]
    )
    assert Decimal(journal["total_debit"]) == 100
    for basis, currency in (("BASE", "INR"), ("ORIGINAL", "USD")):
        balance = await client.get(
            BASE + "/ledger/balance",
            params={
                "as_of": "2026-04-05",
                "basis": basis,
                "currency": currency,
                "account_id": customer["id"],
            },
            headers=ledger_headers(),
        )
        assert balance.status_code == 200 and Decimal(balance.json()["balance"]) == 0, balance.text
    result2 = await client.post(
        BASE + f"/allocations/{result.json()['id']}/reverse",
        json={
            "expected_version": result.json()["row_version"],
            "posting_date": "2026-04-06",
            "reason": "Reallocate settlement",
        },
        headers=ledger_headers(features={"multi_currency"}),
    )
    assert result2.status_code == 200 and result2.json()["fx_reversal_id"], result2.text
    outstanding = await client.get(
        BASE + f"/open-items/{debt['id']}/balance?as_of=2026-04-06", headers=ledger_headers()
    )
    assert (
        Decimal(outstanding.json()["remaining"]) == 100
        and Decimal(outstanding.json()["base_remaining"]) == 8300
    )
    balance = await client.get(
        BASE + "/ledger/balance",
        params={"as_of": "2026-04-06", "currency": "INR", "account_id": customer["id"]},
        headers=ledger_headers(),
    )
    assert Decimal(balance.json()["balance"]) == -100
