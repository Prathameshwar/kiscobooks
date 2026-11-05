"""Adversarial draft, report, and allocation integrity checks."""

import uuid
from decimal import Decimal

import httpx
from billing_platform.db import tenant_scope
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.ledger import DocumentSequence, Journal, JournalLine
from tests.conftest import TENANT
from tests.test_allocations import allocate, items
from tests.test_finance_boundaries import command
from tests.test_finance_review2 import policy as denial
from tests.test_fiscal_api import BASE, facts
from tests.test_ledger_api import create_journal, journal_setup, ledger_headers, post_journal
from tests.test_masters import post
from tests.test_openings_sources import party_accounts, post_source, source


async def test_journal_validation_and_reporting_inputs(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    party, customer, supplier = await party_accounts(client)
    first = body["lines"][0]
    cases = [
        (body | {"posting_date": "2026-03-31"}, 422),
        (body | {"lines": [first | {"account_id": str(uuid.uuid4())}, body["lines"][1]]}, 404),
        (body | {"lines": [first | {"account_id": customer["id"]}, body["lines"][1]]}, 409),
        (body | {"lines": [line | {"currency": "USD"} for line in body["lines"]]}, 409),
    ]
    for value, code in cases:
        result = await command(client, "/journals/preview", value)
        assert result.status_code == code, result.text
    foreign = body | {"lines": [line | {"currency": "USD"} for line in body["lines"]]}
    result = await command(client, "/journals/preview", foreign, features={"multi_currency"})
    assert result.status_code == 422
    for entity, field in (
        ("journal", "total_debit"),
        ("journal_line", "amount"),
        ("account", "posting_policy"),
    ):
        denied = await command(client, "/journals/preview", body, policies=[denial(entity, field)])
        assert denied.status_code == 403, denied.text
    accounts = (await client.get(BASE + "/accounts?limit=200", headers=ledger_headers())).json()[
        "items"
    ]
    general = next(row for row in accounts if row["id"] == body["lines"][1]["account_id"])
    draft_account = await post(
        client,
        "/accounts",
        {
            "code": "DRAFT_POST",
            "name": "Not activated",
            "group_id": general["group_id"],
            "kind": "GENERAL",
        },
    )
    invalid = body | {"lines": [first | {"account_id": draft_account["id"]}, body["lines"][1]]}
    assert (await command(client, "/journals/preview", invalid)).status_code == 409
    invoice = await source(client, customer, general["id"])
    assert (await post_source(client, invoice)).status_code == 200
    query = {"as_of": "2026-04-30", "currency": "INR", "party_id": party["id"]}
    ledger = await client.get(BASE + "/ledger/balance", params=query, headers=ledger_headers())
    assert ledger.status_code == 200 and Decimal(ledger.json()["balance"]) == 100
    wrong_currency = await client.get(
        BASE + "/ledger/balance", params=query | {"currency": "USD"}, headers=ledger_headers()
    )
    assert wrong_currency.status_code == 422
    aged = await client.get(
        BASE + "/subledger/ageing",
        params=query | {"role": "CUSTOMER", "account_id": customer["id"]},
        headers=ledger_headers(),
    )
    assert aged.status_code == 200 and Decimal(aged.json()["debt"]) == 100
    wrong_role = await client.get(
        BASE + "/subledger/ageing",
        params=query | {"role": "CUSTOMER", "account_id": supplier["id"]},
        headers=ledger_headers(),
    )
    assert wrong_role.status_code == 403


async def test_corrupt_prepared_values_and_exhausted_numbering_never_post(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, authority = await journal_setup(client, app)
    first = await create_journal(client, body)
    assert (await post_journal(client, first)).status_code == 200
    row = await create_journal(client, body)
    journal_id = uuid.UUID(row["id"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            line = await db.scalar(select(JournalLine).where(JournalLine.journal_id == journal_id))
            assert line is not None
            line.base_amount += Decimal(1)
    invalid = await post_journal(client, row)
    assert invalid.status_code == 409 and "conversion" in invalid.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            line = await db.scalar(select(JournalLine).where(JournalLine.journal_id == journal_id))
            assert line is not None
            line.base_amount -= Decimal(1)
    authority.fail = True
    assert (await post_journal(client, row)).status_code == 503
    authority.fail = False
    changed = await post_journal(
        client, row, finance=facts().model_copy(update={"configuration_hash": "b" * 64})
    )
    assert changed.status_code == 409 and "configuration" in changed.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.get(Journal, journal_id)
            assert stored is not None
            stored.total_debit += Decimal(1)
            stored.total_credit += Decimal(1)
    invalid = await post_journal(client, row)
    assert invalid.status_code == 409 and "conversion" in invalid.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.get(Journal, journal_id)
            assert stored is not None
            stored.total_debit -= Decimal(1)
            stored.total_credit -= Decimal(1)
            sequence = await db.scalar(
                select(DocumentSequence).where(DocumentSequence.series_key == "MANUAL")
            )
            assert sequence is not None
            sequence.next_value = 999999999
    exhausted = await post_journal(client, row)
    assert exhausted.status_code == 409 and "exhausted" in exhausted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            stored = await db.get(Journal, journal_id)
            assert stored is not None and stored.status == "PREPARED" and stored.number is None
    for object_id, date in ((row["id"], "2026-04-03"), (first["id"], "2026-04-01")):
        invalid = await command(
            client,
            f"/journals/{object_id}/reversal",
            {"posting_date": date, "reason": "Invalid reversal"},
        )
        assert invalid.status_code == 409
    invalid = await command(
        client,
        f"/journals/{first['id']}/void",
        {"expected_version": 3, "reason": "Cannot void posted money"},
    )
    assert invalid.status_code == 409


async def test_allocation_rejects_missing_authority_and_reversed_history(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client, currency="USD")
    invoice = await source(
        client, customer, journal["lines"][1]["account_id"], currency="USD", rate="83"
    )
    receipt = await source(
        client,
        customer,
        journal["lines"][0]["account_id"],
        kind="RECEIPT",
        currency="USD",
        rate="84",
        date="2026-04-05",
    )
    assert (await post_source(client, invoice)).status_code == 200
    assert (await post_source(client, receipt)).status_code == 200
    stored_items = await items(client)
    debt, credit = (
        next(row for row in stored_items if row["direction"] == side) for side in ("DEBT", "CREDIT")
    )
    assert (await allocate(client, debt, credit, "1", "2026-04-04")).status_code == 409
    fx = {"fx_account_id": journal["lines"][1]["account_id"]}
    receipt_id = uuid.UUID(receipt["journal_id"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.get(Journal, receipt_id)
            assert stored is not None
            stored.status = "PREPARED"
    rejected = await allocate(client, debt, credit, "10", "2026-04-05", **fx)
    assert rejected.status_code == 409 and "authority" in rejected.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.get(Journal, receipt_id)
            assert stored is not None
            stored.status = "POSTED"
            original_features = list(stored.features)
            stored.features = []
    rejected = await allocate(client, debt, credit, "10", "2026-04-05", **fx)
    assert rejected.status_code == 409 and "authorization" in rejected.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.get(Journal, receipt_id)
            assert stored is not None
            stored.features = original_features
    allocated = await allocate(client, debt, credit, "10", "2026-04-05", **fx)
    assert allocated.status_code == 201, allocated.text
    path = f"/allocations/{allocated.json()['id']}/reverse"
    body = {"expected_version": 99, "posting_date": "2026-04-06", "reason": "Wrong amount"}
    assert (await command(client, path, body, features={"multi_currency"})).status_code == 409
    body["expected_version"] = allocated.json()["row_version"]
    assert (await command(client, path, body, features={"multi_currency"})).status_code == 200
    reverse = await command(
        client,
        f"/journals/{receipt['journal_id']}/reversal",
        {"posting_date": "2026-04-06", "reason": "Canceled receipt"},
        features={"multi_currency"},
    )
    assert reverse.status_code == 201, reverse.text
    assert (
        await post_journal(client, reverse.json(), features={"multi_currency"})
    ).status_code == 200
    assert (await allocate(client, debt, credit, "10", "2026-04-07", **fx)).status_code == 409
