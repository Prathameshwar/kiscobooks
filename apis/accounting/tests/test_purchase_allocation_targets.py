"""Allocation targets must be real, compatible and open before posting; a bad one is a rejection."""

import copy
import dataclasses
import datetime as dt
import logging
import uuid
from contextlib import contextmanager
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.money import BillAllocation
from voucher_execution.transport import command_digest

from accounting.api.auth import delegated_access
from accounting.models.invoice import InvoiceRecord
from accounting.models.ledger import Journal
from accounting.models.masters import Account
from accounting.models.subledger import Allocation, OpenItem
from accounting.models.voucher_execution import VoucherSourceGuard
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks import allocation_targets
from accounting.tasks.invoice_execution import request_for
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_invoice_execution import fresh_invoice, invoice_command, run
from tests.test_invoice_preview import authority, connection
from tests.test_ledger_api import journal_setup
from tests.test_money_profiles import revise
from tests.test_openings_sources import party_accounts, post_source, source
from tests.test_voucher_money import money_command


@contextmanager
def target_check_disabled(monkeypatch):
    """Model a command whose accepted calculation predates, or bypassed, the early check."""

    async def skipped(*args, **kwargs):
        return None

    with monkeypatch.context() as scoped:
        scoped.setattr(allocation_targets, "check_allocation_targets", skipped)
        yield


async def world(client, app):
    template = await invoice_command(client, app, kind="PURCHASE")
    invoice = copy.deepcopy(template.source_payload["invoice"])
    invoice.update(components=[], accepted_calculation_hash=None, tenders=[])
    invoice["supplies"][0]["amount"] = "1000"
    return template, invoice, connection(client, app)


def advance_against(invoice, item_id, amount="500"):
    return {
        "allocation_key": str(uuid7()),
        "debt": {"line_key": invoice["party_line_key"]},
        "credit": {"item_id": str(item_id)},
        "currency": "INR",
        "amount": amount,
    }


async def post_item(client, app, account_id, *, kind="PAYMENT", amount="600"):
    """Post a source document on a party account and return the open item it created."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cash = await db.scalar(select(Account).where(Account.kind == "CASH"))
            known = set(await db.scalars(select(OpenItem.id)))
    row = await source(client, {"id": account_id}, str(cash.id), kind=kind, amount=amount)
    assert (await post_source(client, row)).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            created = [item for item in await db.scalars(select(OpenItem)) if item.id not in known]
    assert len(created) == 1
    return created[0]


async def assert_nothing_executed(app, *, intents=None, open_items=0):
    """Rejected content leaves no live intent, journal, invoice fact, allocation or receipt."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            statuses = list(await db.scalars(select(VoucherMoneyIntent.status)))
            if intents is not None:
                assert statuses == intents
            assert set(statuses) <= {"CANCELLED"}
            assert set(
                await db.scalars(select(Journal.status).where(Journal.kind == "VOUCHER"))
            ) <= {"VOID"}
            # Prepared facts of a cancelled intent stay as immutable evidence; none may be live.
            assert not await db.scalar(
                select(func.count(InvoiceRecord.id))
                .join(VoucherMoneyIntent, VoucherMoneyIntent.id == InvoiceRecord.intent_id)
                .where(VoucherMoneyIntent.status != "CANCELLED")
            )
            assert await db.scalar(select(func.count(OpenItem.id))) == open_items
            assert await db.scalar(select(func.count(Allocation.id))) == 0
            assert set(await db.scalars(select(VoucherSourceGuard.committed_execution_id))) <= {
                None
            }


async def test_missing_credit_item_is_refused_at_prepare_without_any_intent(
    client, app, monkeypatch
):
    template, invoice, transport = await world(client, app)
    invoice["allocations"] = [advance_against(invoice, uuid7())]
    with target_check_disabled(monkeypatch):
        command = await fresh_invoice(app, template, transport, kind="PURCHASE", invoice=invoice)
    result = await run(app, command)
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED"
    assert await run(app, command) == result
    await assert_nothing_executed(app, intents=[])


async def test_missing_credit_item_found_only_at_commit_is_a_content_rejection(
    client, app, monkeypatch, caplog
):
    """Defense in depth: a 404 from the owner must never escape dispatch as a retryable error."""
    template, invoice, transport = await world(client, app)
    invoice["allocations"] = [advance_against(invoice, uuid7())]
    with target_check_disabled(monkeypatch):
        command = await fresh_invoice(app, template, transport, kind="PURCHASE", invoice=invoice)
        with caplog.at_level(logging.ERROR, logger="accounting.voucher_execution"):
            result = await run(app, command)
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED"
    # Operators learn the rule class from a sanitized diagnostic, never the message or ids.
    assert '"event":"voucher.execution.content_rejected"' in caplog.text
    assert '"error_type":"NotFoundError"' in caplog.text
    assert str(command.execution_id) not in caplog.text
    with target_check_disabled(monkeypatch):
        assert await run(app, command) == result
    await assert_nothing_executed(app, intents=["CANCELLED"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert list(await db.scalars(select(Journal.status))) == ["VOID"]


async def test_missing_debt_item_of_a_receipt_is_a_content_rejection_not_a_404(
    client, app, monkeypatch
):
    original, period, owner = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    original["lines"][1]["account_id"] = customer["id"]
    body = await money_command(app, original, period)
    financial = body.source_payload["financial"]
    financial["accounts"][1]["tracking"] = "ON_ACCOUNT"
    financial["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": str(uuid7())},
            "credit": {"line_key": financial["accounts"][1]["line_key"]},
            "currency": "INR",
            "amount": "60",
        }
    ]
    body = revise(body, kind="RECEIPT", financial=financial)
    result = await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED", result
    assert (
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
        == result
    )
    await assert_nothing_executed(app, intents=[])
    # The same content reaching commit unchecked is still a rejection, never a 404.
    again = body.model_copy(update={"operation_id": uuid7(), "execution_id": uuid7()})
    again = again.model_copy(update={"request_hash": command_digest(again)})
    with target_check_disabled(monkeypatch):
        late = await dispatch(
            app.state.session_factory, again, secret=SECRET.encode(), client=owner
        )
    assert late.outcome == "REJECTED" and late.rejection_code == "CONTENT_REJECTED", late


def preview_of(template, invoice):
    candidate = template.model_copy(
        update={"source_payload": dict(template.source_payload) | {"invoice": invoice}}
    )
    return request_for(candidate).model_copy(update={"authority": authority()[0]})


async def refused(transport, template, invoice, fragment):
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(preview_of(template, invoice))
    assert error.value.response.status_code == 422, error.value.response.text
    assert fragment in error.value.response.text


async def test_preview_refuses_unusable_advance_targets_and_accepts_a_usable_one(client, app):
    template, invoice, transport = await world(client, app)
    supplier = invoice["party_account_id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            customer = str((await db.scalar(select(Account).where(Account.code == "CUSTOMER"))).id)
    advance = await post_item(client, app, supplier, kind="PAYMENT", amount="600")
    owed = await post_item(client, app, supplier, kind="BILL", amount="300")
    other_account = await post_item(client, app, customer, kind="RECEIPT", amount="600")
    assert (advance.direction, owed.direction, other_account.direction) == (
        "CREDIT",
        "DEBT",
        "CREDIT",
    )
    # First use of an account bumps its version; the preview must name the current ones.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            invoice["party_account_version"] = (
                await db.get(Account, uuid.UUID(supplier))
            ).row_version
            for line in invoice["supplies"]:
                line["account_version"] = (
                    await db.get(Account, uuid.UUID(line["account_id"]))
                ).row_version

    cases = (
        (advance_against(invoice, uuid7()), "does not exist"),
        (advance_against(invoice, owed.id, "100"), "a debt bill and a credit bill"),
        (advance_against(invoice, other_account.id), "same party role, account and currency"),
        (advance_against(invoice, advance.id, "600.0001"), "exceeds the available outstanding"),
        (
            advance_against(invoice, advance.id) | {"currency": "USD"},
            "currency differs",
        ),
    )
    for allocation, fragment in cases:
        await refused(transport, template, invoice | {"allocations": [allocation]}, fragment)

    usable = invoice | {"allocations": [advance_against(invoice, advance.id, "600")]}
    accepted = await transport.preview(preview_of(template, usable))
    assert accepted.payable == Decimal("1000") and type(accepted.payable) is Decimal


async def test_item_of_another_company_is_indistinguishable_from_a_missing_item(
    client, app, monkeypatch
):
    # An actor scoped to one company is already refused by require_inputs for another; neutralize
    # it so the query's own company filter is what separates the two companies here.
    monkeypatch.setattr(allocation_targets, "require_inputs", lambda access: None)
    template, invoice, _ = await world(client, app)
    advance = await post_item(client, app, invoice["party_account_id"], amount="600")
    delegated, _company = authority()
    mine = delegated_access(
        delegated, SECRET.encode(), tenant_id=TENANT, company_id=COMPANY, actor_user_id=USER
    )
    foreign = dataclasses.replace(
        mine, context=mine.context.model_copy(update={"company_id": uuid7()})
    )
    allocation = BillAllocation.model_validate(advance_against(invoice, advance.id, "100"))
    new_bill = {
        allocation.debt.line_key: allocation_targets.NewBill(advance.account_id, advance.currency)
    }
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            await allocation_targets.check_allocation_targets(
                db, mine, [allocation], posting_date=dt.date(2026, 4, 2), new_bills=new_bill
            )
            with pytest.raises(ValidationFailedError, match="does not exist"):
                await allocation_targets.check_allocation_targets(
                    db, foreign, [allocation], posting_date=dt.date(2026, 4, 2), new_bills=new_bill
                )


async def test_purchase_with_a_usable_advance_still_posts_exactly_as_before(client, app):
    template, invoice, transport = await world(client, app)
    advance = await post_item(client, app, invoice["party_account_id"], amount="600")
    invoice["allocations"] = [advance_against(invoice, advance.id, "500")]
    command = await fresh_invoice(app, template, transport, kind="PURCHASE", invoice=invoice)
    result = await run(app, command)
    assert result.outcome == "COMMITTED", result
    assert await run(app, command) == result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journal = await db.scalar(
                select(Journal).where(Journal.source_id == str(command.execution_id))
            )
            assert journal.status == "POSTED" and journal.number.startswith("PURCHASE/")
            assert journal.total_debit == journal.total_credit == Decimal("1000")
            assert type(journal.total_debit) is Decimal
            bill = await db.scalar(select(OpenItem).where(OpenItem.direction == "DEBT"))
            allocation = await db.scalar(select(Allocation))
            assert allocation.debt_item_id == bill.id and allocation.credit_item_id == advance.id
            assert allocation.amount == Decimal("500") and type(allocation.amount) is Decimal
            assert bill.amount == Decimal("1000")


async def test_plain_two_line_purchase_without_allocation_or_tender_still_posts(client, app):
    """No target to prove means no extra queries or permissions: the bill posts as it always did."""
    template, invoice, transport = await world(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rent = await db.scalar(select(Account).where(Account.code == "RENT"))
    invoice["supplies"][0]["amount"] = "700"
    invoice["supplies"].append(
        dict(
            invoice["supplies"][0],
            line_key=str(uuid7()),
            account_id=str(rent.id),
            account_version=rent.row_version,
            description="Office rent",
            amount="300",
        )
    )
    invoice["allocations"] = []
    command = await fresh_invoice(app, template, transport, kind="PURCHASE", invoice=invoice)
    result = await run(app, command)
    assert result.outcome == "COMMITTED", result
    assert await run(app, command) == result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journal = await db.scalar(
                select(Journal).where(Journal.source_id == str(command.execution_id))
            )
            assert journal.status == "POSTED" and journal.number.startswith("PURCHASE/")
            assert journal.total_debit == journal.total_credit == Decimal("1000")
            assert type(journal.total_debit) is Decimal
            bill = await db.scalar(select(OpenItem))
            assert bill.direction == "DEBT" and bill.amount == Decimal("1000")
            assert await db.scalar(select(func.count(OpenItem.id))) == 1
            assert await db.scalar(select(func.count(Allocation.id))) == 0
            record = await db.scalar(select(InvoiceRecord))
            assert record.payable == Decimal("1000")
