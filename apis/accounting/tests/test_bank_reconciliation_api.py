"""Persisted bank evidence cannot turn offsetting unmatched entries into a closed session."""

import asyncio
import base64
import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.models.masters import AccountBankProfile
from tests.conftest import TENANT
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import (
    LEDGER_PERMISSIONS,
    create_journal,
    journal_setup,
    ledger_headers,
    post_journal,
)
from tests.test_money_profiles import bank_account

PATH = BASE + "/bank-reconciliation"


async def setup(client, app):
    original, _period, _owner = await journal_setup(client, app)
    bank = await bank_account(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            profile = await db.scalar(
                select(AccountBankProfile).where(
                    AccountBankProfile.account_id == uuid.UUID(bank["id"])
                )
            )
            assert profile is not None
            profile.reconciliation_start_date = dt.date(2026, 4, 1)
    created = await client.post(
        PATH + "/mappings",
        json={
            "account_id": bank["id"],
            "currency": "INR",
            "date_column": "date",
            "debit_column": "debit",
            "credit_column": "credit",
            "reference_column": "ref",
            "description_column": "description",
            "transaction_id_column": "transaction_id",
        },
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    policy = await client.post(
        PATH + "/policies",
        json={
            "account_id": bank["id"],
            "mode": "SUGGEST_AND_REVIEW",
            "match_window_days": 30,
            "require_separate_reviewer": False,
        },
        headers=ledger_headers(),
    )
    assert policy.status_code == 201, policy.text
    return bank, created.json(), original


async def test_reviewed_import_and_false_zero_session(client, app):
    bank, mapping, _original = await setup(client, app)
    raw = (
        b"date,debit,credit,ref,description,transaction_id\n"
        b"2026-04-02,100,,A,Debit from bank,TX-1\n"
        b"2026-04-03,,100,B,Credit to bank,TX-2\n"
    )
    body = {
        "mapping_id": mapping["id"],
        "content_base64": base64.b64encode(raw).decode(),
        "period_from": "2026-04-01",
        "period_to": "2026-04-30",
        "opening_balance": "0",
        "closing_balance": "0",
    }

    async def upload_once():
        return await client.post(PATH + "/imports", json=body, headers=ledger_headers())

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        first, replay = await upload_once(), await upload_once()
    else:
        first, replay = await asyncio.gather(upload_once(), upload_once())
    assert first.status_code == 201, first.text
    assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]
    committed = await client.post(
        PATH + f"/imports/{first.json()['id']}/commit",
        json={"reason": "Reviewed bank statement"},
        headers=ledger_headers(),
    )
    assert committed.status_code == 200, committed.text
    overlap_raw = raw.replace(b"TX-2", b"TX-3")
    overlap_preview = await client.post(
        PATH + "/imports",
        json=body | {"content_base64": base64.b64encode(overlap_raw).decode()},
        headers=ledger_headers(),
    )
    assert overlap_preview.status_code == 201, overlap_preview.text
    overlap_commit = await client.post(
        PATH + f"/imports/{overlap_preview.json()['id']}/commit",
        json={"reason": "Reviewed overlapping export"},
        headers=ledger_headers(),
    )
    assert overlap_commit.status_code == 409, overlap_commit.text
    rejected_overlap = await client.post(
        PATH + f"/imports/{overlap_preview.json()['id']}/reject",
        json={"reason": "Overlapping export cannot join the approved balance chain"},
        headers=ledger_headers(),
    )
    assert rejected_overlap.status_code == 200
    assert rejected_overlap.json()["status"] == "REJECTED"
    entries = await client.get(
        PATH + f"/imports/{first.json()['id']}/rows", headers=ledger_headers()
    )
    entry_id = entries.json()[0]["id"]
    proposed = await client.post(
        PATH + "/proposals",
        json={"statement_entry_id": entry_id, "kind": "PAYMENT", "reason": "Missing bank fee"},
        headers=ledger_headers(),
    )
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["status"] == "PREPARED"
    premature = await client.post(
        PATH + f"/proposals/{proposed.json()['id']}/resolve",
        json={"voucher_id": str(uuid.uuid4()), "reason": "Try without posted voucher"},
        headers=ledger_headers(),
    )
    assert premature.status_code == 409, premature.text
    rejected = await client.post(
        PATH + f"/proposals/{proposed.json()['id']}/reject",
        json={"reason": "Fee belonged to a different account"},
        headers=ledger_headers(),
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    session = await client.post(
        PATH + "/sessions",
        json={
            "account_id": bank["id"],
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
            "opening_balance": "0",
            "closing_balance": "0",
            "reason": "April bank review",
        },
        headers=ledger_headers(),
    )
    assert session.status_code == 201, session.text
    assert session.json()["snapshot"]["balance_agrees"] is True
    assert session.json()["snapshot"]["rows_covered"] is False
    closed = await client.post(
        PATH + f"/sessions/{session.json()['id']}/finalize",
        json={"reason": "Attempted finalization"},
        headers=ledger_headers(),
    )
    assert closed.status_code == 409, closed.text


async def test_statement_import_requires_its_distinct_scope(client, app):
    bank, _mapping, _original = await setup(client, app)
    denied = await client.post(
        PATH + "/mappings",
        json={
            "account_id": bank["id"],
            "currency": "INR",
            "date_column": "date",
            "debit_column": "debit",
            "credit_column": "credit",
            "reference_column": "ref",
            "description_column": "description",
        },
        headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"accounting.statement.import"}),
    )
    assert denied.status_code == 403
    hidden = await client.get(
        PATH + "/mappings",
        params={"account_id": bank["id"]},
        headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"accounting.statement.read"}),
    )
    assert hidden.status_code == 403


async def test_exact_bank_match_closes_statement_without_posting_again(client, app):
    bank, mapping, original = await setup(client, app)
    original["lines"][0]["account_id"] = bank["id"]
    journal = await create_journal(client, original)
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    from accounting.models.ledger import JournalLine

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            line = await db.scalar(
                select(JournalLine).where(JournalLine.account_id == uuid.UUID(bank["id"]))
            )
            assert line is not None
            line_id = line.id
    adopted = await client.post(
        BASE + "/bank-instruments/adopt",
        json={
            "journal_line_id": str(line_id),
            "expected_journal_version": posted.json()["row_version"],
            "mode": "UPI",
            "reference": "UPI-1",
            "evidence_date": "2026-04-02",
            "reason": "Legacy bank book evidence",
        },
        headers=ledger_headers(),
    )
    assert adopted.status_code == 201, adopted.text
    raw = (
        b"date,debit,credit,ref,description,transaction_id\n"
        b"2026-04-03,,100.25,UPI-1,Received,TX-1\n"
    )
    imported = await client.post(
        PATH + "/imports",
        json={
            "mapping_id": mapping["id"],
            "content_base64": base64.b64encode(raw).decode(),
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
            "opening_balance": "0",
            "closing_balance": "100.25",
        },
        headers=ledger_headers(),
    )
    assert imported.status_code == 201, imported.text
    committed = await client.post(
        PATH + f"/imports/{imported.json()['id']}/commit",
        json={"reason": "Reviewed bank file"},
        headers=ledger_headers(),
    )
    assert committed.status_code == 200, committed.text
    rows = await client.get(
        PATH + f"/imports/{imported.json()['id']}/rows", headers=ledger_headers()
    )
    assert rows.status_code == 200 and len(rows.json()) == 1
    import_id = rows.json()[0]["id"]
    candidates = await client.get(PATH + f"/rows/{import_id}/candidates", headers=ledger_headers())
    assert candidates.status_code == 200, candidates.text
    assert candidates.json()[0]["instrument_id"] == adopted.json()["id"]
    previewed = await client.post(
        PATH + "/matches/preview",
        json={
            "group_id": str(uuid7()),
            "parts": [
                {
                    "statement_entry_id": import_id,
                    "instrument_id": adopted.json()["id"],
                    "amount": "100.25",
                }
            ],
            "reason": "Preview exact UPI receipt",
        },
        headers=ledger_headers(),
    )
    assert previewed.status_code == 200, previewed.text
    assert Decimal(previewed.json()["statement_residuals"][import_id]) == 0
    history = await client.get(
        PATH + "/matches", params={"statement_entry_id": import_id}, headers=ledger_headers()
    )
    assert history.status_code == 200 and history.json() == []

    async def competing_match():
        return await client.post(
            PATH + "/matches",
            json={
                "group_id": str(uuid7()),
                "parts": [
                    {
                        "statement_entry_id": import_id,
                        "instrument_id": adopted.json()["id"],
                        "amount": "100.25",
                    }
                ],
                "reason": "Matched UPI receipt",
            },
            headers=ledger_headers(),
        )

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        outcomes = [await competing_match(), await competing_match()]
    else:
        outcomes = await asyncio.gather(competing_match(), competing_match())
    assert sorted(response.status_code for response in outcomes) in ([201, 409], [201, 422])
    matched = next(response for response in outcomes if response.status_code == 201)
    assert matched.status_code == 201, matched.text
    session = await client.post(
        PATH + "/sessions",
        json={
            "account_id": bank["id"],
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
            "opening_balance": "0",
            "closing_balance": "100.25",
            "reason": "April statement review",
        },
        headers=ledger_headers(),
    )
    assert session.status_code == 201, session.text
    assert session.json()["snapshot"]["rows_covered"] is True
    finalized = await client.post(
        PATH + f"/sessions/{session.json()['id']}/finalize",
        json={"reason": "Reviewed closing"},
        headers=ledger_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == "FINALIZED"
    blocked = await client.post(
        PATH + f"/matches/{matched.json()[0]['id']}/unmatch",
        json={"reason": "Try unlink"},
        headers=ledger_headers(),
    )
    assert blocked.status_code == 409
    later_draft = await create_journal(client, original)
    backdated = await post_journal(client, later_draft)
    assert backdated.status_code == 409, backdated.text
    overlapping_session = await client.post(
        PATH + "/sessions",
        json={
            "account_id": bank["id"],
            "period_from": "2026-04-01",
            "period_to": "2026-05-31",
            "opening_balance": "0",
            "closing_balance": "100.25",
            "reason": "Overlapping April and May",
        },
        headers=ledger_headers(),
    )
    assert overlapping_session.status_code == 409, overlapping_session.text


async def test_pre_cutover_clearance_is_not_an_opening_uncleared_item(client, app):
    bank, mapping, original = await setup(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            profile = await db.scalar(
                select(AccountBankProfile).where(
                    AccountBankProfile.account_id == uuid.UUID(bank["id"])
                )
            )
            assert profile is not None
            profile.reconciliation_start_date = dt.date(2026, 5, 1)
    original["lines"][0]["account_id"] = bank["id"]
    journal = await create_journal(client, original)
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    from accounting.models.ledger import JournalLine

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            line = await db.scalar(
                select(JournalLine).where(JournalLine.account_id == uuid.UUID(bank["id"]))
            )
            assert line is not None
            line_id = line.id
    adopted = await client.post(
        BASE + "/bank-instruments/adopt",
        json={
            "journal_line_id": str(line_id),
            "expected_journal_version": posted.json()["row_version"],
            "mode": "UPI",
            "reference": "OLD-UPI",
            "evidence_date": "2026-04-02",
            "reason": "Existing bank movement",
        },
        headers=ledger_headers(),
    )
    assert adopted.status_code == 201, adopted.text
    event_path = BASE + f"/bank-instruments/{adopted.json()['id']}/events"
    previous = (await client.get(event_path, headers=ledger_headers())).json()["items"][0]
    cleared = await client.post(
        event_path,
        json={
            "expected_event_id": previous["id"],
            "action": "CLEARED",
            "event_date": "2026-04-05",
            "reason": "April bank advice",
        },
        headers=ledger_headers(),
    )
    assert cleared.status_code == 201, cleared.text
    raw = (
        b"date,debit,credit,ref,description,transaction_id\n"
        b"2026-05-02,1,,MAY-1,Debit,NEW-1\n"
        b"2026-05-03,,1,MAY-2,Credit,NEW-2\n"
    )
    imported = await client.post(
        PATH + "/imports",
        json={
            "mapping_id": mapping["id"],
            "content_base64": base64.b64encode(raw).decode(),
            "period_from": "2026-05-01",
            "period_to": "2026-05-31",
            "opening_balance": "100.25",
            "closing_balance": "100.25",
        },
        headers=ledger_headers(),
    )
    assert imported.status_code == 201, imported.text
    committed = await client.post(
        PATH + f"/imports/{imported.json()['id']}/commit",
        json={"reason": "Reviewed May file"},
        headers=ledger_headers(),
    )
    assert committed.status_code == 200, committed.text
    session = await client.post(
        PATH + "/sessions",
        json={
            "account_id": bank["id"],
            "period_from": "2026-05-01",
            "period_to": "2026-05-31",
            "opening_balance": "100.25",
            "closing_balance": "100.25",
            "reason": "May bank controls",
        },
        headers=ledger_headers(),
    )
    assert session.status_code == 201, session.text
    snapshot = session.json()["snapshot"]
    assert snapshot["missing_opening_items"] == 0
    assert Decimal(snapshot["outstanding_book_amount"]) == 0
    assert snapshot["precleared_instrument_ids"] == [adopted.json()["id"]]
