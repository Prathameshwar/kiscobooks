"""Charge history follows allocations, reversals and explicit policy eligibility."""

import uuid
from decimal import Decimal

import httpx
from billing_platform.db import tenant_scope
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.ledger import JournalLine
from tests.conftest import TENANT
from tests.test_allocations import allocate, items
from tests.test_charges_api import approve, assessment, setup_charge
from tests.test_finance_boundaries import command
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import ledger_headers, post_journal
from tests.test_openings_sources import post_source, source


async def test_unallocation_restores_charge_principal_on_its_date(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, account, journal, _ = await setup_charge(client, app)
    payment = await source(
        client,
        account,
        journal["lines"][0]["account_id"],
        kind="RECEIPT",
        amount="50",
        date="2026-04-08",
    )
    assert (await post_source(client, payment)).status_code == 200
    rows = await items(client)
    debt, credit = (
        next(row for row in rows if row["direction"] == kind) for kind in ("DEBT", "CREDIT")
    )
    allocated = await allocate(client, debt, credit, "50", "2026-04-08")
    assert allocated.status_code == 201
    before = await command(client, "/charge-assessments/preview", body)
    assert before.status_code == 200 and Decimal(before.json()["amount"]) == Decimal("0.75")
    reversed_allocation = await command(
        client,
        f"/allocations/{allocated.json()['id']}/reverse",
        {
            "expected_version": allocated.json()["row_version"],
            "posting_date": "2026-04-10",
            "reason": "Reallocate payment",
        },
    )
    assert reversed_allocation.status_code == 200
    after = await command(client, "/charge-assessments/preview", body)
    assert after.status_code == 200 and Decimal(after.json()["amount"]) == Decimal("0.9")
    assert after.json()["snapshot"]["allocations"][0]["reversal_date"] == "2026-04-10"
    invalid = await command(client, "/charge-assessments/preview", body | {"item_id": credit["id"]})
    assert invalid.status_code == 409
    row = await assessment(client, body)
    approved = await approve(client, row)
    assert approved.status_code == 200
    assert (await post_source(client, approved.json())).status_code == 200
    charged_item = next(
        row for row in await items(client) if row["id"] not in {debt["id"], credit["id"]}
    )
    excluded = await command(
        client,
        "/charge-assessments/preview",
        body
        | {
            "item_id": charged_item["id"],
            "coverage_end_date": "2026-04-25",
            "posting_date": "2026-04-25",
            "due_date": "2026-04-25",
        },
    )
    assert excluded.status_code == 409 and "charges on charges" in excluded.text
    next_row = await assessment(
        client, body | {"coverage_end_date": "2026-04-20", "posting_date": "2026-04-20"}
    )
    reverse = await command(
        client,
        f"/journals/{approved.json()['journal_id']}/reversal",
        {"posting_date": "2026-04-20", "reason": "Later run pending"},
    )
    assert reverse.status_code == 409 and "later charge" in reverse.text
    rejected = await command(
        client,
        f"/charge-assessments/{next_row['id']}/reject",
        {"expected_version": 1, "reason": "Cancel later run"},
    )
    assert rejected.status_code == 200
    reverse = await command(
        client,
        f"/journals/{approved.json()['journal_id']}/reversal",
        {"posting_date": "2026-04-20", "reason": "Correct earlier run"},
    )
    assert reverse.status_code == 201
    assert (await post_journal(client, reverse.json())).status_code == 200


async def test_charge_journal_cannot_drift_from_approved_evidence(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _, _ = await setup_charge(client, app)
    row = await assessment(client, body)
    approved = await approve(client, row)
    assert approved.status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            lines = list(
                await db.scalars(
                    select(JournalLine).where(
                        JournalLine.journal_id == uuid.UUID(approved.json()["journal_id"])
                    )
                )
            )
            for line in lines:
                line.amount += Decimal(1)
                line.base_amount += Decimal(1)
    invalid = await post_source(client, approved.json())
    assert invalid.status_code == 409 and "approved calculation" in invalid.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            lines = list(
                await db.scalars(
                    select(JournalLine).where(
                        JournalLine.journal_id == uuid.UUID(approved.json()["journal_id"])
                    )
                )
            )
            for line in lines:
                line.amount -= Decimal(1)
                line.base_amount -= Decimal(1)
    assert (await post_source(client, approved.json())).status_code == 200


async def test_fixed_fee_and_expired_coverage_cannot_create_more_debt(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _, _ = await setup_charge(
        client, app, method="FIXED", rate="10", valid_to="2026-04-25"
    )
    row = await assessment(client, body)
    approved = await approve(client, row)
    assert approved.status_code == 200
    assert (await post_source(client, approved.json())).status_code == 200
    next_body = body | {"coverage_end_date": "2026-04-20", "posting_date": "2026-04-20"}
    preview = await command(client, "/charge-assessments/preview", next_body)
    assert preview.status_code == 200 and Decimal(preview.json()["amount"]) == 0
    assert (await command(client, "/charge-assessments", next_body)).status_code == 409
    expired = await command(
        client,
        "/charge-assessments/preview",
        body
        | {
            "coverage_end_date": "2026-04-27",
            "posting_date": "2026-04-27",
            "due_date": "2026-04-27",
        },
    )
    assert expired.status_code == 409 and "effective dates" in expired.text
    path = BASE + "/charge-assessments/" + row["id"]
    current = await client.get(path, headers=ledger_headers())
    assert current.json()["status"] == "POSTED"
