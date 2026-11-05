"""Ordinary native money execution against the real persistence boundary."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal

import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.transport import command_digest

from accounting.models.ledger import DocumentSequence, Journal, JournalLine
from accounting.models.masters import Account
from accounting.models.voucher_money import BankInstrument, BankInstrumentEvent, VoucherMoneyIntent
from accounting.tasks.journal_posting import PostingDependencyError
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import SECRET, TENANT
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_voucher_execution import command


async def test_cancellation_wins_while_identity_reservation_is_in_flight(client, app):
    import asyncio

    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    entered, released = asyncio.Event(), asyncio.Event()
    reserve = owner.reserve

    async def delayed(*args, **kwargs):
        entered.set()
        await released.wait()
        return await reserve(*args, **kwargs)

    owner.reserve = delayed
    task = asyncio.create_task(
        dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    )
    await asyncio.wait_for(entered.wait(), 20)
    try:
        result = await dispatch(
            app.state.session_factory,
            body.model_copy(update={"purpose": "CANCEL"}),
            secret=SECRET.encode(),
            client=owner,
        )
        assert result.outcome == "CANCELLED"
    finally:
        released.set()
    assert (await asyncio.wait_for(task, 20)).outcome == "CANCELLED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(DocumentSequence.id))) == 0
            assert (await db.scalar(select(Journal))).status == "VOID"


def delegated(**kwargs):
    values = ledger_headers(
        permissions=LEDGER_PERMISSIONS | {"vouchers.post", "vouchers.reverse"}, **kwargs
    )
    company = verify_company_context(
        values["X-Company-Context"], values["X-Company-Signature"], SECRET.encode()
    )
    context, signature = sign_company_context(
        company.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return DelegatedAuthority(
        actor_context=values["X-Actor-Context"],
        actor_signature=values["X-Actor-Signature"],
        company_context=context,
        company_signature=signature,
    )


async def money_command(app, original, period, **kwargs):
    entries = []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for line in original["lines"]:
                account = await db.get(Account, uuid.UUID(line["account_id"]))
                entries.append(
                    line | {"line_key": str(uuid7()), "source_version": account.row_version}
                )
    financial = {
        "purpose": "GENERAL",
        "accounts": entries,
        "tenders": [
            {
                "tender_key": str(uuid7()),
                "line_key": entries[0]["line_key"],
                "mode": "CASH",
                "currency": "INR",
                "amount": entries[0]["amount"],
            }
        ],
    }
    payload = {
        "mode": "ACCOUNTS",
        "lines": [],
        "posting_date": original["posting_date"],
        "document_date": original["document_date"],
        "narration": original["description"],
        "financial": financial,
    }
    evidence = {
        "kind": "JOURNAL",
        "profile": "STANDARD",
        "company_configuration_hash": "a" * 64,
        "policy": {"financial": {"journal_cash_bank_allowed": True}},
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    body = command(
        period,
        protocol_version=2,
        source_payload=payload,
        content_hash=hashlib.sha256(canonical_json(payload)).hexdigest(),
        configuration_hash=digest,
        configuration_evidence=evidence | {"digest": digest},
        authority=delegated(),
        **kwargs,
    )
    return body.model_copy(update={"request_hash": command_digest(body)})


async def test_journal_posts_one_number_and_native_tender_with_lost_ack_replay(client, app):
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    result = await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    assert result.outcome == "COMMITTED"
    assert (
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
        == result
    )
    assert owner.calls == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journal = await db.scalar(select(Journal).where(Journal.kind == "VOUCHER"))
            assert journal.status == "POSTED" and journal.number.startswith("JOURNAL/")
            assert isinstance(journal.total_debit, Decimal) and journal.total_debit == Decimal(
                "100.25"
            )
            assert await db.scalar(select(func.count(JournalLine.id))) == 2
            assert (await db.scalar(select(DocumentSequence))).next_value == 2
            assert (await db.scalar(select(BankInstrument))).amount == Decimal("100.25")
            assert (await db.scalar(select(BankInstrumentEvent))).action == "BOOKED"


async def test_authority_outage_leaves_durable_intent_and_cancel_is_terminal(client, app):
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    owner.fail = True
    with pytest.raises(PostingDependencyError):
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(VoucherMoneyIntent))).status == "PREPARED"
            assert await db.scalar(select(func.count(DocumentSequence.id))) == 0
    cancel = body.model_copy(update={"purpose": "CANCEL"})
    result = await dispatch(app.state.session_factory, cancel, secret=SECRET.encode(), client=owner)
    assert result.outcome == "CANCELLED"
    owner.fail = False
    assert (
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
        == result
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(Journal))).status == "VOID"
            assert await db.scalar(select(func.count(BankInstrument.id))) == 0


async def test_closed_period_after_prepare_releases_reservation_without_effect(client, app):
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    owner.fail = True
    with pytest.raises(PostingDependencyError):
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    # Public journal posting must not bypass the voucher receipt transaction.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journal = await db.scalar(select(Journal))
            identity, version = journal.id, journal.row_version
    from tests.test_fiscal_api import BASE

    bypass = await client.post(
        BASE + f"/journals/{identity}/post",
        json={"expected_version": version},
        headers=ledger_headers(),
    )
    assert bypass.status_code == 409
    voided = await client.post(
        BASE + f"/journals/{identity}/void",
        json={"expected_version": version, "reason": "Try bypassing owner cancellation"},
        headers=ledger_headers(),
    )
    assert voided.status_code == 409


async def test_journal_reversal_is_atomic_and_duplicate_reversal_is_rejected(client, app):
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    result = await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    assert result.outcome == "COMMITTED"
    reverse = body.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": body.execution_id,
            "correction_reason": "Correct erroneous cash entry",
            "posting_date": dt.date(2026, 4, 3),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "authority": delegated(),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    reversed_result = await dispatch(
        app.state.session_factory, reverse, secret=SECRET.encode(), client=owner
    )
    assert reversed_result.outcome == "COMMITTED"
    assert (
        await dispatch(app.state.session_factory, reverse, secret=SECRET.encode(), client=owner)
        == reversed_result
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journals = list(await db.scalars(select(Journal)))
            assert len(journals) == 2 and all(row.status == "POSTED" for row in journals)
            correction = next(row for row in journals if row.kind == "REVERSAL")
            assert correction.reversal_of_id == next(
                row.id for row in journals if row.kind == "VOUCHER"
            )
            history = list(
                await db.scalars(select(BankInstrumentEvent).order_by(BankInstrumentEvent.id))
            )
            assert [row.action for row in history] == ["BOOKED", "REVERSED"]


async def test_pure_bill_adjustment_and_reversal_create_no_cash_journal(client, app):
    from accounting.models.subledger import Allocation
    from tests.test_allocations import items
    from tests.test_openings_sources import party_accounts, post_source, source

    original, period, owner = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    invoice = await source(client, customer, original["lines"][1]["account_id"])
    receipt = await source(
        client, customer, original["lines"][0]["account_id"], kind="RECEIPT", date="2026-04-03"
    )
    for row in (invoice, receipt):
        assert (await post_source(client, row)).status_code == 200
    open_items = await items(client)
    debt = next(row for row in open_items if row["direction"] == "DEBT")
    credit = next(row for row in open_items if row["direction"] == "CREDIT")
    body = await money_command(app, original, period)
    payload = body.source_payload | {
        "posting_date": "2026-04-03",
        "financial": {
            "purpose": "BILL_ADJUSTMENT",
            "allocations": [
                {
                    "allocation_key": str(uuid7()),
                    "debt": {"item_id": debt["id"]},
                    "credit": {"item_id": credit["id"]},
                    "currency": "INR",
                    "amount": "40",
                }
            ],
        },
    }
    body = body.model_copy(
        update={
            "source_payload": payload,
            "posting_date": dt.date(2026, 4, 3),
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
            "authority": delegated(),
        }
    )
    body = body.model_copy(update={"request_hash": command_digest(body)})
    result = await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    assert result.outcome == "COMMITTED" and not any(
        ref.effect_kind == "JOURNAL" for ref in result.effects
    )
    reverse = body.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": body.execution_id,
            "correction_reason": "Reallocate selected bill",
            "posting_date": dt.date(2026, 4, 4),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "authority": delegated(),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    assert (
        await dispatch(app.state.session_factory, reverse, secret=SECRET.encode(), client=owner)
    ).outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == 2
            allocation = await db.scalar(select(Allocation))
            assert allocation.amount == Decimal("40") and allocation.reversal_date == dt.date(
                2026, 4, 4
            )


async def test_receipt_settles_foreign_bill_and_reverses_cash_and_realized_fx_atomically(
    client, app
):
    from accounting.models.subledger import Allocation
    from tests.test_allocations import items
    from tests.test_money_profiles import revise
    from tests.test_openings_sources import party_accounts, post_source, source

    original, period, owner = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client, currency="USD")
    offset = original["lines"][1]["account_id"]
    invoice = await source(client, customer, offset, currency="USD", rate="83")
    assert (await post_source(client, invoice)).status_code == 200
    debt = next(row for row in await items(client) if row["direction"] == "DEBT")
    original["lines"][0]["amount"] = "8400"
    original["lines"][1].update(
        account_id=customer["id"], currency="USD", amount="100", exchange_rate="84"
    )
    body = await money_command(app, original, period)
    financial = body.source_payload["financial"]
    financial["accounts"][1]["tracking"] = "ON_ACCOUNT"
    financial["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": debt["id"]},
            "credit": {"line_key": financial["accounts"][1]["line_key"]},
            "currency": "USD",
            "amount": "100",
            "fx_account_id": offset,
        }
    ]
    body = revise(
        body, kind="RECEIPT", financial=financial, policy={"foreign_currency_allowed": True}
    )
    body = body.model_copy(update={"authority": delegated(features={"multi_currency"})})
    body = body.model_copy(update={"request_hash": command_digest(body)})
    result = await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    assert result.outcome == "COMMITTED", result
    assert (
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
        == result
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            allocation = await db.scalar(select(Allocation))
            fx = await db.get(Journal, allocation.fx_journal_id)
            assert fx.kind == "REALIZED_FX" and type(fx.total_debit) is Decimal
            assert fx.total_debit == Decimal("100")
            cash = await db.scalar(select(BankInstrument))
            assert cash.amount == Decimal("8400") and cash.currency == "INR"
    reverse = body.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": body.execution_id,
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "posting_date": dt.date(2026, 4, 3),
            "correction_reason": "Correct foreign receipt",
            "authority": delegated(features={"multi_currency"}),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    reversed_result = await dispatch(
        app.state.session_factory, reverse, secret=SECRET.encode(), client=owner
    )
    assert reversed_result.outcome == "COMMITTED", reversed_result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            allocation = await db.scalar(select(Allocation))
            assert allocation.reversal_date == dt.date(2026, 4, 3) and allocation.fx_reversal_id
            assert await db.scalar(select(func.count(Journal.id))) == 5
            assert await db.scalar(select(func.count(BankInstrument.id))) == 1
