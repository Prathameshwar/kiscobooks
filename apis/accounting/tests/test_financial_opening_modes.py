"""Approved migration policies: unknown dates, clearing and explicit YTD provenance."""

import datetime as dt
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.subledger import OpenItem
from accounting.tasks.posting_delivery import deliver
from tests.conftest import TENANT
from tests.test_allocations import allocate, items
from tests.test_financial_opening_api import ROOT, body_for
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import ledger_headers, post_journal
from tests.test_masters import activate, post
from tests.test_openings_sources import party_accounts, post_source, source


def action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_version": row["expected_version"],
        "manifest_hash": row["manifest_hash"],
        "reason": "Reviewed migration evidence",
    }


async def prepare(client: httpx.AsyncClient, row: dict[str, Any], **headers: Any) -> dict[str, Any]:
    result = await client.post(
        ROOT + f"/{row['id']}/prepare-drafts", json=action(row), headers=ledger_headers(**headers)
    )
    assert result.status_code == 200, result.text
    return result.json()


async def post_child(client: httpx.AsyncClient, identity: str, **headers: Any) -> httpx.Response:
    row = (
        await client.get(BASE + "/journals/" + identity, headers=ledger_headers(**headers))
    ).json()
    return await post_journal(client, row, **headers)


async def general(client: httpx.AsyncClient, *, nature: str = "ASSET") -> str:
    heads = (await client.get(BASE + "/account-heads", headers=ledger_headers())).json()["items"]
    head = next(row for row in heads if row["code"] == nature)
    group = await post(
        client,
        "/account-groups",
        {"code": "MIGRATION", "name": "Migration bridge", "head_id": head["id"]},
        h=ledger_headers(),
    )
    group = await activate(client, "/account-groups", group, h=ledger_headers())
    row = await post(
        client,
        "/accounts",
        {
            "code": "MIGRATION",
            "name": "Migration clearing",
            "group_id": group["id"],
            "kind": "GENERAL",
        },
        h=ledger_headers(),
    )
    row = await activate(client, "/accounts", row, h=ledger_headers())
    return str(row["id"])


async def test_unknown_on_account_preserves_null_dates_ages_separately_and_settles(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body = await body_for(client, app)
    cash = body["entries"][0]["account_id"]
    party, customer, _ = await party_accounts(client)
    body["entries"][0].update(
        account_id=customer["id"],
        documents=[
            {
                "source_key": "unknown-principal",
                "document_kind": "ON_ACCOUNT",
                "reference": "Reviewed on-account opening",
                "amount": "100.25",
            }
        ],
    )
    saved = await client.post(ROOT, json=body, headers=ledger_headers())
    assert saved.status_code == 201, saved.text
    row = await prepare(client, saved.json())
    posted = await post_child(client, row["journal_ids"][0])
    assert posted.status_code == 200, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            item = await db.scalar(select(OpenItem))
            assert item is not None and item.document_date is None and item.due_date is None
            assert item.terms["history_unknown"] and item.terms["tracking"] == "ON_ACCOUNT"
            identity = str(item.id)
    query = {"as_of": "2026-04-10", "party_id": party["id"], "role": "CUSTOMER", "currency": "INR"}
    aged = await client.get(BASE + "/subledger/ageing", params=query, headers=ledger_headers())
    assert aged.status_code == 200 and Decimal(aged.json()["unknown_due"]) == Decimal(
        "100.25"
    ), aged.text
    assert Decimal(aged.json()["days_91_plus"]) == 0
    risk = await client.post(
        BASE + "/credit/check",
        json={
            "account_id": customer["id"],
            "currency": "INR",
            "amount": "1",
            "exchange_rate": "1",
            "posting_date": "2026-04-10",
        },
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert risk.status_code == 200 and Decimal(risk.json()["unknown_due"]) == Decimal(
        "100.25"
    ), risk.text
    assert risk.json()["overdue_history_complete"] is False
    charge = await client.post(
        BASE + "/charge-assessments/preview",
        json={
            "item_id": identity,
            "policy_id": str(uuid7()),
            "exchange_rate": "1",
            "coverage_end_date": "2026-04-10",
            "posting_date": "2026-04-10",
            "due_date": "2026-04-10",
        },
        headers=ledger_headers(),
    )
    assert charge.status_code == 409 and "unknown" in charge.text, charge.text
    await deliver(app.state.session_factory, app.state.posting_client)
    path = ROOT + "/" + row["id"]
    row = (await client.get(path, headers=ledger_headers())).json()
    finalized = await client.post(path + "/finalize", json=action(row), headers=ledger_headers())
    assert finalized.status_code == 200, finalized.text
    receipt = await source(client, customer, cash, kind="RECEIPT", amount="40", date="2026-04-05")
    assert (await post_source(client, receipt)).status_code == 200
    open_items = await items(client)
    debt = next(item for item in open_items if item["direction"] == "DEBT")
    credit = next(item for item in open_items if item["direction"] == "CREDIT")
    allocated = await allocate(client, debt, credit, "40", "2026-04-05")
    assert allocated.status_code == 201, allocated.text
    aged = await client.get(BASE + "/subledger/ageing", params=query, headers=ledger_headers())
    assert Decimal(aged.json()["unknown_due"]) == Decimal("60.25"), aged.text


@pytest.mark.parametrize("correction", [False, True])
async def test_large_opening_resumes_with_zero_clearing_or_recovers_partial_posting(
    client: httpx.AsyncClient, app: FastAPI, correction: bool
) -> None:
    body = await body_for(client, app)
    body["clearing_account_id"] = await general(client)
    original = body["entries"]
    body["entries"] = [
        entry | {"source_key": f"entry-{index}-{side}"}
        for index in range(201)
        for side, entry in enumerate(original)
    ]
    saved = await client.post(ROOT, json=body, headers=ledger_headers())
    assert saved.status_code == 201, saved.text
    path = ROOT + "/" + saved.json()["id"]
    row = await prepare(client, saved.json())
    assert len(row["journal_ids"]) == 2 and "OPENING_DRAFTS_NOT_PREPARED" in row["blockers"]
    row = await prepare(client, row)
    assert len(row["journal_ids"]) == 3
    result = await post_child(client, row["journal_ids"][0])
    assert result.status_code == 200, result.text
    current = (await client.get(path, headers=ledger_headers())).json()
    blocked = await client.post(path + "/finalize", json=action(current), headers=ledger_headers())
    assert blocked.status_code == 409, blocked.text
    reconciliation = await client.get(path + "/reconciliation", headers=ledger_headers())
    assert Decimal(reconciliation.json()["clearing_balance"]) != 0, reconciliation.text
    if correction:
        reversal = await client.post(
            BASE + f"/journals/{row['journal_ids'][0]}/reversal",
            json={"posting_date": "2026-04-01", "reason": "Correct partial opening"},
            headers=ledger_headers(),
        )
        assert reversal.status_code == 201, reversal.text
        result = await post_journal(client, reversal.json())
        assert result.status_code == 200, result.text
        current = (await client.get(path, headers=ledger_headers())).json()
        recovered = await client.post(
            path + "/void", json=action(current), headers=ledger_headers()
        )
        assert (
            recovered.status_code == 200 and recovered.json()["status"] == "REVERSED"
        ), recovered.text
        return
    for identity in row["journal_ids"][1:]:
        result = await post_child(client, identity)
        assert result.status_code == 200, result.text
    await deliver(app.state.session_factory, app.state.posting_client)
    current = (await client.get(path, headers=ledger_headers())).json()
    reconciliation = await client.get(path + "/reconciliation", headers=ledger_headers())
    assert (
        reconciliation.json()["ready_to_finalize"]
        and Decimal(reconciliation.json()["clearing_balance"]) == 0
    ), reconciliation.text
    finalized = await client.post(
        path + "/finalize", json=action(current), headers=ledger_headers()
    )
    assert (
        finalized.status_code == 200 and finalized.json()["status"] == "FINALIZED"
    ), finalized.text


async def test_midyear_ytd_is_explicit_balanced_and_published_as_provenance(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from accounting.models.fiscal import FinancialSetup
    from accounting.models.subledger import OpeningBatch
    from accounting.tasks.reporting_feed import fact
    from tests.test_fiscal_api import facts

    body = await body_for(client, app)
    income = await general(client, nature="INCOME")
    current_facts = facts().model_copy(
        update={"books_begin_date": dt.date(2026, 4, 2), "configuration_hash": "b" * 64}
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            setup = await db.scalar(select(FinancialSetup))
            assert setup is not None
            setup.books_begin_date = dt.date(2026, 4, 2)
    body.update(
        posting_date="2026-04-02",
        covered_through="2026-04-01",
        originating_year_start="2026-04-01",
        coverage_mode="YTD_SUMMARY",
        ytd_summary=[
            {
                "account_id": income,
                "side": "CREDIT",
                "currency": "INR",
                "amount": "100.25",
                "base_amount": "100.25",
            }
        ],
    )
    body["entries"][1]["account_id"] = income
    bad = await client.post(
        ROOT + "/preview",
        json=body | {"ytd_summary": []},
        headers=ledger_headers(finance=current_facts),
    )
    assert bad.status_code == 422, bad.text
    saved = await client.post(ROOT, json=body, headers=ledger_headers(finance=current_facts))
    assert saved.status_code == 201, saved.text
    row = await prepare(client, saved.json(), finance=current_facts)
    posted = await post_child(client, row["journal_ids"][0], finance=current_facts)
    assert posted.status_code == 200, posted.text
    await deliver(app.state.session_factory, app.state.posting_client)
    path = ROOT + "/" + row["id"]
    row = (await client.get(path, headers=ledger_headers(finance=current_facts))).json()
    finalized = await client.post(
        path + "/finalize", json=action(row), headers=ledger_headers(finance=current_facts)
    )
    assert finalized.status_code == 200, finalized.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            batch = await db.scalar(select(OpeningBatch))
            assert batch is not None
            wire = fact(batch, "opening_batch", batch.id)
            assert wire.data is not None and wire.data["coverage"]["mode"] == "YTD_SUMMARY"
            assert wire.data["coverage"]["ytd_summary"][0]["base_amount"] == "100.25"
            assert len(wire.data["journal_ids"]) == 1
