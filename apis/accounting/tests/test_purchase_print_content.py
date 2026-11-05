"""Print facts carry Accounting's own voucher number and ledger names, under native field rights."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError
from sqlalchemy import select
from voucher_execution.printing import PurchasePrintCommand

from accounting.models.invoice import InvoiceRecord
from accounting.models.ledger import Journal
from accounting.models.masters import Account
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks import purchase_print
from accounting.tasks.invoice_execution import request_for
from tests.conftest import TENANT
from tests.test_invoice_execution import invoice_command, run
from tests.test_invoice_preview import connection
from tests.test_purchase_print_supplier import deny, prepared, reader


async def posted_journal(app, execution):
    """The journal that posted this execution's invoice record, read straight from the tables."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            record = await db.scalar(
                select(InvoiceRecord).where(InvoiceRecord.revision_id == execution.revision_id)
            )
            intent = await db.get(VoucherMoneyIntent, record.intent_id)
            return await db.get(Journal, intent.journal_id)


async def test_posted_print_carries_the_journal_number_and_a_preview_never_does(client, app):
    execution, _, _, transport, command = await prepared(client, app)
    draft = await transport.purchase_print(command(reader()))
    # Numbers are allocated on posting only (invariant 6), so nothing exists to print yet.
    assert draft.source == "PREVIEW" and draft.voucher_number is None
    assert (await run(app, execution)).outcome == "COMMITTED"
    journal = await posted_journal(app, execution)
    assert journal.number
    posted = await transport.purchase_print(command(reader(), posted=True))
    assert posted.source == "POSTED"
    assert posted.voucher_number == journal.number
    assert posted.voucher_number.startswith("PURCHASE/")


async def test_unreadable_journal_number_is_withheld_without_failing_the_print(
    client, app, monkeypatch
):
    execution, _, _, transport, command = await prepared(client, app)
    assert (await run(app, execution)).outcome == "COMMITTED"
    real = purchase_print.require_fields

    def number_is_denied(current, name, fields, *, row=None):
        if name == "journal" and "number" in fields:
            raise PermissionDeniedError("financial calculation inputs are not readable")
        real(current, name, fields, row=row)

    # A field policy on `number` cannot be shown through the signed API here: any read deny already
    # masks the frozen supply evidence, which refuses a POSTED print outright (conservative, and
    # unchanged). The field check itself must still withhold only the number, never fail.
    monkeypatch.setattr(purchase_print, "require_fields", number_is_denied)
    restricted = await transport.purchase_print(command(reader(), posted=True))
    # The number is None so Vouchers prints "Not allocated"; amounts stay readable.
    assert restricted.source == "POSTED" and restricted.voucher_number is None
    assert restricted.calculation.payable > 0
    assert [row.name for row in restricted.ledgers]  # ledger names are separately checked


async def test_a_denied_journal_status_still_refuses_the_posted_print(client, app):
    execution, _, _, transport, command = await prepared(client, app)
    assert (await run(app, execution)).outcome == "COMMITTED"
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.purchase_print(
            command(reader(policies=[deny("journal", "status")]), posted=True)
        )
    assert error.value.response.status_code == 403


async def test_each_line_names_its_expense_ledger_for_draft_and_posted_prints(client, app):
    execution, _, _, transport, command = await prepared(client, app)
    invoice = execution.source_payload["invoice"]
    line = uuid.UUID(invoice["supplies"][0]["line_key"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            expense = await db.get(Account, uuid.UUID(invoice["supplies"][0]["account_id"]))
    draft = await transport.purchase_print(command(reader()))
    assert {row.key: row.name for row in draft.ledgers} == {line: expense.name}
    assert (await run(app, execution)).outcome == "COMMITTED"
    posted = await transport.purchase_print(command(reader(), posted=True))
    assert {row.key: row.name for row in posted.ledgers} == {line: expense.name}


async def test_a_restricted_ledger_name_is_withheld_not_substituted(client, app):
    execution, payable, _, transport, command = await prepared(client, app)
    invoice = execution.source_payload["invoice"]
    line = uuid.UUID(invoice["supplies"][0]["line_key"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            expense = await db.get(Account, uuid.UUID(invoice["supplies"][0]["account_id"]))
    # Deny the name of the expense ledger only; the supplier's payable ledger stays readable.
    only_expense = {
        **deny("account", "name"),
        "condition": {"field": "code", "cmp": "eq", "value": expense.code},
    }
    assert payable.code != expense.code
    result = await transport.purchase_print(command(reader(policies=[only_expense])))
    assert [(row.key, row.name) for row in result.ledgers] == [(line, None)]
    assert result.calculation.payable > 0


async def test_cash_tenders_name_their_cash_or_bank_ledger(client, app):
    execution = await invoice_command(client, app, kind="PURCHASE", cash=True)
    transport = connection(client, app)
    tender = execution.source_payload["invoice"]["tenders"][0]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cash = await db.get(Account, uuid.UUID(tender["account_id"]))
    preview = request_for(execution).model_copy(update={"authority": reader()})
    command = PurchasePrintCommand(
        preview=preview, revision_id=execution.revision_id, require_posted=False
    )
    draft = await transport.purchase_print(command)
    names = {row.key: row.name for row in draft.ledgers}
    assert names[uuid.UUID(tender["tender"]["tender_key"])] == cash.name
    assert len(names) == 2  # the expense line and the tender, each exactly once
    assert (await run(app, execution)).outcome == "COMMITTED"
    posted = await transport.purchase_print(command.model_copy(update={"require_posted": True}))
    assert {row.key: row.name for row in posted.ledgers} == names
