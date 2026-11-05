"""Native Payment/Receipt/Contra and manual banking evidence."""

import hashlib
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.transport import command_digest

from accounting.models.ledger import Journal, JournalLine
from accounting.models.subledger import OpenItem
from accounting.models.voucher_money import BankInstrument, BankInstrumentEvent
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import SECRET, TENANT
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import create_journal, journal_setup, ledger_headers, post_journal
from tests.test_masters import activate, post
from tests.test_openings_sources import party_accounts
from tests.test_voucher_money import money_command


def revise(command, *, kind=None, financial=None, policy=None):
    kind = kind or command.kind
    payload = command.source_payload | ({"financial": financial} if financial is not None else {})
    evidence = {k: v for k, v in command.configuration_evidence.items() if k != "digest"}
    evidence["kind"] = kind
    if policy:
        evidence["policy"] = {"financial": policy}
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    value = command.model_copy(
        update={
            "kind": kind,
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
            "configuration_evidence": evidence | {"digest": digest},
            "configuration_hash": digest,
        }
    )
    return value.model_copy(update={"request_hash": command_digest(value)})


async def bank_account(client):
    bank_id = uuid7()
    h = ledger_headers(bank_ids={bank_id})
    groups = (await client.get(BASE + "/account-groups?limit=200", headers=h)).json()["items"]
    group = next(row["id"] for row in groups if row["code"] == "BANKS")
    bank = await post(
        client,
        "/accounts",
        {"code": "MAINBANK", "name": "Main Bank", "kind": "BANK", "group_id": group},
        h=h,
    )
    await post(
        client,
        "/account-bank-profiles",
        {"account_id": bank["id"], "company_bank_id": str(bank_id)},
        h=h,
    )
    return await activate(client, "/accounts", bank, h=h)


async def test_legacy_receipt_counts_voucher_cash_in_daily_party_limit(client, app):
    from decimal import Decimal

    from tests.test_fiscal_api import facts
    from tests.test_openings_sources import source

    original, period, owner = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    original["lines"][1]["account_id"] = customer["id"]
    command = await money_command(app, original, period)
    financial = command.source_payload["financial"]
    financial["accounts"][1]["tracking"] = "ON_ACCOUNT"
    command = revise(command, kind="RECEIPT", financial=financial)
    assert (
        await dispatch(app.state.session_factory, command, secret=SECRET.encode(), client=owner)
    ).outcome == "COMMITTED"
    legacy = await source(
        client, customer, original["lines"][0]["account_id"], kind="RECEIPT", amount="40"
    )
    journal = (
        await client.get(BASE + f"/journals/{legacy['journal_id']}", headers=ledger_headers())
    ).json()
    posted = await post_journal(
        client, journal, finance=facts().model_copy(update={"cash_receipt_limit": Decimal("120")})
    )
    assert posted.status_code == 409, posted.text


@pytest.mark.parametrize(
    "kind,role,purpose",
    [
        ("RECEIPT", "CUSTOMER", "ADVANCE"),
        ("PAYMENT", "SUPPLIER", "ADVANCE"),
        ("PAYMENT", "CUSTOMER", "REFUND"),
        ("RECEIPT", "SUPPLIER", "REFUND"),
    ],
)
async def test_payment_receipt_advances_refunds_keep_explicit_open_items(
    client, app, kind, role, purpose
):
    original, period, owner = await journal_setup(client, app)
    _, customer, supplier = await party_accounts(client)
    original["lines"][1]["account_id"] = (customer if role == "CUSTOMER" else supplier)["id"]
    if kind == "PAYMENT":
        original["lines"][0]["side"], original["lines"][1]["side"] = "CREDIT", "DEBIT"
    command = await money_command(app, original, period)
    financial = command.source_payload["financial"]
    financial["purpose"] = purpose
    financial["accounts"][1]["tracking"] = "ADVANCE" if purpose == "ADVANCE" else "ON_ACCOUNT"
    command = revise(command, kind=kind, financial=financial)
    result = await dispatch(
        app.state.session_factory, command, secret=SECRET.encode(), client=owner
    )
    assert result.outcome == "COMMITTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            item = await db.scalar(select(OpenItem))
            assert item.role == role and item.direction == (
                "CREDIT" if purpose == "ADVANCE" else "DEBT"
            )
            assert item.terms["tracking"] == financial["accounts"][1]["tracking"]
            assert (await db.scalar(select(Journal))).number.startswith(kind + "/")


async def test_contra_and_split_cheques_post_once_and_clearing_does_not_move_cash(client, app):
    original, period, owner = await journal_setup(client, app)
    bank = await bank_account(client)
    original["lines"][1]["account_id"] = bank["id"]
    command = await money_command(app, original, period)
    financial = command.source_payload["financial"]
    financial["purpose"] = "TRANSFER"
    financial["tenders"] += [
        {
            "tender_key": str(uuid7()),
            "line_key": financial["accounts"][1]["line_key"],
            "mode": "CHEQUE",
            "reference": ref,
            "amount": amount,
            "currency": "INR",
            "instrument_date": "2026-04-05",
        }
        for ref, amount in (("CHEQUE-A", "40"), ("CHEQUE-B", "60.25"))
    ]
    command = revise(command, kind="CONTRA", financial=financial)
    result = await dispatch(
        app.state.session_factory, command, secret=SECRET.encode(), client=owner
    )
    assert result.outcome == "COMMITTED", result
    page = await client.get(BASE + "/bank-instruments?limit=2", headers=ledger_headers())
    assert page.status_code == 200 and page.json()["page"]["has_more"]
    assert "reference" not in page.json()["items"][0]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            instrument = await db.scalar(
                select(BankInstrument).where(BankInstrument.mode == "CHEQUE")
            )
            identity = instrument.id
    path = BASE + f"/bank-instruments/{identity}/events"
    previous = (await client.get(path, headers=ledger_headers())).json()["items"][0]
    body = {
        "expected_event_id": previous["id"],
        "action": "CLEARED",
        "event_date": "2026-04-03",
        "reason": "Bank advice received",
    }
    assert (await client.post(path, json=body, headers=ledger_headers())).status_code == 422
    key = ledger_headers()
    body["event_date"] = "2026-04-05"
    cleared = await client.post(path, json=body, headers=key)
    assert cleared.status_code == 201, cleared.text
    replay = await client.post(path, json=body, headers=key)
    assert replay.json()["id"] == cleared.json()["id"]
    assert (await client.post(path, json=body, headers=ledger_headers())).status_code == 409
    reconciled = await client.post(
        path,
        json=body
        | {
            "expected_event_id": cleared.json()["id"],
            "action": "RECONCILED",
            "reference": "STATEMENT-APR",
        },
        headers=ledger_headers(),
    )
    assert reconciled.status_code == 201, reconciled.text
    assert (await client.get(path, headers=ledger_headers(permissions=set()))).status_code == 403
    assert (await client.get(path)).status_code == 401
    other = uuid7()
    from tests.conftest import COMPANY

    assert (
        await client.get(
            path.replace(str(COMPANY), str(other)), headers=ledger_headers(company=other)
        )
    ).status_code == 403
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == 1
            event = await db.scalar(select(BankInstrumentEvent))
            event.action = "CLEARED"
            with pytest.raises(ConflictError):
                await db.flush()


async def test_adopt_legacy_bank_entry_cannot_duplicate_or_change_money(client, app):
    original, _, _ = await journal_setup(client, app)
    bank = await bank_account(client)
    original["lines"][0]["account_id"] = bank["id"]
    journal = await create_journal(client, original)
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            line = await db.scalar(
                select(JournalLine).where(JournalLine.account_id == uuid.UUID(bank["id"]))
            )
            identity = str(line.id)
    body = {
        "journal_line_id": identity,
        "expected_journal_version": posted.json()["row_version"],
        "mode": "BANK_TRANSFER",
        "reference": "IMPORT-REF",
        "evidence_date": "2026-04-03",
        "reason": "Reviewed opening evidence",
    }
    key = ledger_headers()
    adopted = await client.post(BASE + "/bank-instruments/adopt", json=body, headers=key)
    assert adopted.status_code == 201, adopted.text
    assert adopted.json()["amount"] == "100.2500" and adopted.json()["intent_id"] is None
    replay = await client.post(BASE + "/bank-instruments/adopt", json=body, headers=key)
    assert replay.json()["id"] == adopted.json()["id"]
    assert (
        await client.post(BASE + "/bank-instruments/adopt", json=body, headers=ledger_headers())
    ).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == 1
    reversal = await client.post(
        BASE + f"/journals/{journal['id']}/reversal",
        json={"posting_date": "2026-04-04", "reason": "Correct legacy bank entry"},
        headers=ledger_headers(),
    )
    assert reversal.status_code == 201, reversal.text
    assert (await post_journal(client, reversal.json())).status_code == 200
    history = await client.get(
        BASE + f"/bank-instruments/{adopted.json()['id']}/events", headers=ledger_headers()
    )
    assert [row["action"] for row in history.json()["items"]] == ["BOOKED", "REVERSED"]
