"""Overdue calculation, separate approval, posting, waiver and reversal evidence."""

from decimal import Decimal
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.charges import ChargeAssessment, ChargePolicy
from tests.test_allocations import allocate, items
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers, post_journal
from tests.test_openings_sources import party_accounts, post_source, source


async def setup_charge(
    client: httpx.AsyncClient,
    app: FastAPI,
    *,
    supplier: bool = False,
    tax_treatment: str = "NON_TAXABLE",
    currency: str = "INR",
    exchange_rate: str = "1",
    **policy_values: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    journal, _, _ = await journal_setup(client, app)
    _, customer, creditor = await party_accounts(client, currency=currency)
    account = creditor if supplier else customer
    invoice = await source(
        client,
        account,
        journal["lines"][1]["account_id"],
        kind="BILL" if supplier else "INVOICE",
        due_date="2026-04-02",
        currency=currency,
        rate=exchange_rate,
    )
    assert (await post_source(client, invoice)).status_code == 200
    item = (await items(client))[0]
    policy = await client.post(
        BASE + "/charge-policies",
        json={
            "account_id": account["id"],
            "offset_account_id": journal["lines"][1]["account_id"],
            "currency": currency,
            "valid_from": "2026-04-01",
            "accrual_start_date": "2026-04-01",
            "method": "INTEREST",
            "rate": "36.5",
            "tax_treatment": tax_treatment,
            "tax_reason": "Explicit test exemption",
            **policy_values,
        },
        headers=ledger_headers(),
    )
    assert policy.status_code == 201, policy.text
    request = {
        "item_id": item["id"],
        "policy_id": policy.json()["id"],
        "coverage_end_date": "2026-04-13",
        "posting_date": "2026-04-13",
        "due_date": "2026-04-20",
        "exchange_rate": exchange_rate,
    }
    return request, account, journal, invoice


async def assessment(client: httpx.AsyncClient, request: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        BASE + "/charge-assessments", json=request, headers=ledger_headers()
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def approve(client: httpx.AsyncClient, row: dict[str, Any], **headers: Any) -> httpx.Response:
    return await client.post(
        BASE + f"/charge-assessments/{row['id']}/approve",
        json={"expected_version": row["row_version"], "reason": "Reviewed calculation and policy"},
        headers=ledger_headers(user=uuid7(), **headers),
    )


async def test_charge_preview_approval_posting_coverage_and_reversal(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    request, account, _, invoice = await setup_charge(client, app)
    preview = await client.post(
        BASE + "/charge-assessments/preview", json=request, headers=ledger_headers()
    )
    assert preview.status_code == 200 and Decimal(preview.json()["amount"]) == 1, preview.text
    row = await assessment(client, request)
    assert (
        await client.post(BASE + "/charge-assessments", json=request, headers=ledger_headers())
    ).status_code == 409
    own = await client.post(
        BASE + f"/charge-assessments/{row['id']}/approve",
        json={"expected_version": 1, "reason": "Own approval"},
        headers=ledger_headers(),
    )
    assert own.status_code == 403
    approved = await approve(client, row)
    assert approved.status_code == 200, approved.text
    posted = await post_source(client, approved.json())
    assert posted.status_code == 200, posted.text
    debt = await client.get(
        BASE + "/ledger/balance",
        params={"as_of": "2026-04-13", "account_id": account["id"], "currency": "INR"},
        headers=ledger_headers(),
    )
    assert Decimal(debt.json()["balance"]) == 101
    repeated = await client.post(
        BASE + "/charge-assessments/preview", json=request, headers=ledger_headers()
    )
    assert repeated.status_code == 409
    blocked = await client.post(
        BASE + f"/journals/{invoice['journal_id']}/reversal",
        json={"posting_date": "2026-04-14", "reason": "Has dependent charge"},
        headers=ledger_headers(),
    )
    assert blocked.status_code == 409
    reverse = await client.post(
        BASE + f"/journals/{approved.json()['journal_id']}/reversal",
        json={"posting_date": "2026-04-14", "reason": "Incorrect charge"},
        headers=ledger_headers(),
    )
    assert reverse.status_code == 201, reverse.text
    assert (await post_journal(client, reverse.json())).status_code == 200
    current = (
        await client.get(BASE + f"/charge-assessments/{row['id']}", headers=ledger_headers())
    ).json()
    assert current["status"] == "REVERSED"
    balance = await client.get(
        BASE + "/ledger/balance",
        params={"as_of": "2026-04-14", "account_id": account["id"], "currency": "INR"},
        headers=ledger_headers(),
    )
    assert Decimal(balance.json()["balance"]) == 100
    with tenant_scope(uuid7()):
        async with app.state.session_factory() as db:
            for model in (ChargePolicy, ChargeAssessment):
                assert await db.scalar(select(func.count(model.id))) == 0


async def test_stale_calculation_rejected_and_waiver_keeps_coverage(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    request, account, journal, _ = await setup_charge(client, app)
    row = await assessment(client, request)
    payment = await source(
        client,
        account,
        journal["lines"][0]["account_id"],
        kind="RECEIPT",
        amount="50",
        date="2026-04-08",
    )
    assert (await post_source(client, payment)).status_code == 200
    all_items = await items(client)
    debt = next(item for item in all_items if item["direction"] == "DEBT")
    credit = next(item for item in all_items if item["direction"] == "CREDIT")
    assert (await allocate(client, debt, credit, "50", "2026-04-08")).status_code == 201
    stale = await approve(client, row)
    assert stale.status_code == 409 and "stale" in stale.text
    rejected = await client.post(
        BASE + f"/charge-assessments/{row['id']}/reject",
        json={"expected_version": 1, "reason": "Recalculate after payment"},
        headers=ledger_headers(),
    )
    assert rejected.status_code == 200
    updated = await assessment(client, request)
    assert Decimal(updated["amount"]) == Decimal("0.75")
    waived = await client.post(
        BASE + f"/charge-assessments/{updated['id']}/waive",
        json={"expected_version": 1, "reason": "Waived as commercial concession"},
        headers=ledger_headers(user=uuid7()),
    )
    assert waived.status_code == 200 and waived.json()["journal_id"] is None, waived.text
    assert (
        await client.post(
            BASE + "/charge-assessments/preview", json=request, headers=ledger_headers()
        )
    ).status_code == 409
    next_preview = await client.post(
        BASE + "/charge-assessments/preview",
        json=request
        | {
            "coverage_end_date": "2026-04-23",
            "posting_date": "2026-04-23",
            "due_date": "2026-04-30",
        },
        headers=ledger_headers(),
    )
    assert next_preview.status_code == 200 and Decimal(next_preview.json()["amount"]) == Decimal(
        "0.50"
    ), next_preview.text
    # Changing past principal after finalized coverage would silently rewrite charges.
    assert (await allocate(client, debt, credit, "1", "2026-04-09")).status_code == 409


async def test_supplier_charge_needs_external_reference(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    request, _, _, _ = await setup_charge(client, app, supplier=True)
    row = await assessment(client, request)
    rejected = await approve(client, row)
    assert rejected.status_code == 409 and "external" in rejected.text
    assert (
        await client.post(
            BASE + f"/charge-assessments/{row['id']}/reject",
            json={"expected_version": 1, "reason": "Add supplier reference"},
            headers=ledger_headers(),
        )
    ).status_code == 200
    valid = await assessment(client, request | {"external_reference": "SUPPLIER-DEBIT-001"})
    approved = await approve(client, valid)
    assert approved.status_code == 200, approved.text
    assert (await post_source(client, approved.json())).status_code == 200
