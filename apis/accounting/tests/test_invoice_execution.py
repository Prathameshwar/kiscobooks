"""Invoices share atomic GL, open-item, tender and durable execution controls."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.transport import command_digest

from accounting.models.fiscal import FiscalPeriod
from accounting.models.invoice import (
    InvoiceAllocationFact,
    InvoiceComponentFact,
    InvoicePostingLine,
    InvoiceRecord,
    InvoiceSupplyFact,
)
from accounting.models.ledger import Journal
from accounting.models.masters import Account
from accounting.models.subledger import Allocation, OpenItem
from accounting.models.voucher_money import BankInstrument
from accounting.tasks.invoice_execution import request_for
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import SECRET, TENANT
from tests.test_invoice_preview import authority, connection, setup
from tests.test_voucher_execution import command
from tests.test_voucher_money import delegated


async def invoice_command(client, app, *, cash=False, kind="SALES"):
    request, transport, supplier = await setup(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            period = await db.scalar(select(FiscalPeriod).where(FiscalPeriod.status == "OPEN"))
            period_value = {"id": str(period.id), "row_version": period.row_version}
            cash_account = await db.scalar(select(Account).where(Account.kind == "CASH"))
            invoice = request.invoice.model_dump(mode="json")
            if kind == "PURCHASE":
                expense = await db.scalar(
                    select(Account).where(Account.code == "NONSTOCK_PURCHASES")
                )
                invoice["party_account_id"] = supplier["id"]
                invoice["party_account_version"] = supplier["row_version"]
                invoice["supplies"][0]["account_id"] = str(expense.id)
                invoice["supplies"][0]["account_version"] = expense.row_version
            if cash:
                key = str(uuid7())
                invoice["tenders"] = [
                    {
                        "account_id": str(cash_account.id),
                        "account_version": cash_account.row_version,
                        "tender": {
                            "tender_key": str(uuid7()),
                            "line_key": key,
                            "mode": "CASH",
                            "amount": "300",
                            "currency": "INR",
                        },
                    }
                ]
    evidence = {
        "kind": kind,
        "profile": "STANDARD",
        "company_configuration_hash": "a" * 64,
        "policy": {"invoice": request.policy.model_dump(mode="json")},
    }
    configuration_hash = hashlib.sha256(canonical_json(evidence)).hexdigest()
    request = type(request).model_validate(
        request.model_dump()
        | {"kind": kind, "configuration_hash": configuration_hash, "invoice": invoice}
    )
    result = await transport.preview(request)
    invoice["accepted_calculation_hash"] = result.calculation_hash
    payload = {
        "mode": "ACCOUNTS",
        "currency": "INR",
        "document_date": "2026-04-02",
        "posting_date": "2026-04-02",
        "lines": [],
        "invoice": invoice,
    }
    body = command(
        period_value,
        protocol_version=2,
        kind=kind,
        source_payload=payload,
        content_hash=hashlib.sha256(canonical_json(payload)).hexdigest(),
        configuration_hash=configuration_hash,
        configuration_evidence=evidence | {"digest": configuration_hash},
        authority=delegated(),
    )
    return body.model_copy(update={"request_hash": command_digest(body)})


async def run(app, body, *, enabled=True):
    return await dispatch(
        app.state.session_factory,
        body,
        secret=SECRET.encode(),
        client=app.state.posting_client,
        invoices_enabled=enabled,
    )


async def test_unsettled_purchase_invoice_reverses_with_original_facts_retained(client, app):
    original = await invoice_command(client, app, kind="PURCHASE")
    posted = await run(app, original)
    assert posted.outcome == "COMMITTED", posted
    reverse = original.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": original.execution_id,
            "correction_reason": "Correct supplier bill",
            "posting_date": dt.date(2026, 4, 3),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "authority": delegated(),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    result = await run(app, reverse)
    assert result.outcome == "COMMITTED", result
    assert await run(app, reverse) == result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(InvoiceRecord.id))) == 1
            journals = list(await db.scalars(select(Journal)))
            assert len(journals) == 2
            assert {row.status for row in journals} == {"POSTED"}
            assert len([row for row in journals if row.reversal_of_id is not None]) == 1


async def fresh_invoice(app, body, transport, *, kind, invoice):
    invoice = dict(invoice)
    invoice["supplies"] = [dict(line) for line in invoice["supplies"]]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            party = await db.get(Account, uuid.UUID(invoice["party_account_id"]))
            invoice["party_account_version"] = party.row_version
            for line in invoice["supplies"]:
                account = await db.get(Account, uuid.UUID(line["account_id"]))
                line["account_version"] = account.row_version
            invoice["tenders"] = [dict(row) for row in invoice.get("tenders", [])]
            for tender in invoice["tenders"]:
                account = await db.get(Account, uuid.UUID(tender["account_id"]))
                tender["account_version"] = account.row_version
    evidence = dict(body.configuration_evidence)
    evidence.pop("digest")
    evidence["kind"] = kind
    configuration_hash = hashlib.sha256(canonical_json(evidence)).hexdigest()
    payload = dict(body.source_payload)
    payload["invoice"] = invoice
    candidate = body.model_copy(
        update={
            "voucher_id": uuid7(),
            "revision_id": uuid7(),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "kind": kind,
            "configuration_hash": configuration_hash,
            "configuration_evidence": evidence | {"digest": configuration_hash},
            "source_payload": payload,
        }
    )
    try:
        calculated = await transport.preview(
            request_for(candidate).model_copy(update={"authority": authority()[0]})
        )
    except httpx.HTTPStatusError as error:
        pytest.fail(error.response.text)
    payload["invoice"] = invoice | {"accepted_calculation_hash": calculated.calculation_hash}
    candidate = candidate.model_copy(
        update={
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
        }
    )
    return candidate.model_copy(update={"request_hash": command_digest(candidate)})


async def test_invoice_posts_full_bill_and_partial_tender_atomically_with_immutable_facts(
    client, app
):
    body = await invoice_command(client, app, cash=True)
    result = await run(app, body)
    assert result.outcome == "COMMITTED", result
    assert await run(app, body) == result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            invoice = await db.scalar(select(InvoiceRecord))
            assert (
                invoice.payable == 900
                and invoice.calculation_hash
                == body.source_payload["invoice"]["accepted_calculation_hash"]
            )
            journal = await db.scalar(select(Journal).where(Journal.kind == "VOUCHER"))
            assert journal.status == "POSTED" and journal.number.startswith("SALES/")
            assert journal.total_debit == journal.total_credit == Decimal("1200")
            items = list(await db.scalars(select(OpenItem).order_by(OpenItem.amount.desc())))
            assert len(items) == 2
            allocation = await db.scalar(select(Allocation))
            assert (
                allocation.debt_item_id == items[0].id and allocation.credit_item_id == items[1].id
            )
            assert items[0].amount == 900 and items[0].amount - allocation.amount == 600
            assert items[1].amount == allocation.amount == 300
            assert (await db.scalar(select(BankInstrument))).amount == 300
            assert await db.scalar(select(func.count(InvoiceSupplyFact.id))) == 1
            assert (await db.scalar(select(InvoiceComponentFact))).amount == -100
            assert await db.scalar(select(func.count(InvoiceAllocationFact.id))) == 2
            assert await db.scalar(select(func.count(InvoicePostingLine.id))) == 4
            invoice.payable = 1
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()


async def test_invoice_release_gate_and_unaccepted_calculation_cannot_create_facts(client, app):
    body = await invoice_command(client, app)
    assert (await run(app, body, enabled=False)).rejection_code == "UNSUPPORTED_PROFILE"
    payload = dict(body.source_payload)
    payload["invoice"] = dict(payload["invoice"], accepted_calculation_hash="0" * 64)
    rejected = body.model_copy(
        update={
            "execution_id": uuid7(),
            "operation_id": uuid7(),
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
        }
    )
    rejected = rejected.model_copy(update={"request_hash": command_digest(rejected)})
    assert (await run(app, rejected)).outcome == "REJECTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(InvoiceRecord.id))) == 0
            assert await db.scalar(select(func.count(Journal.id))) == 0


async def test_purchase_invoice_cash_settlement_uses_supplier_debt_direction(client, app):
    body = await invoice_command(client, app, cash=True, kind="PURCHASE")
    result = await run(app, body)
    assert result.outcome == "COMMITTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            items = list(await db.scalars(select(OpenItem).order_by(OpenItem.amount.desc())))
            assert len(items) == 2
            assert items[0].direction == "DEBT" and items[1].direction == "CREDIT"
            allocation = await db.scalar(select(Allocation))
            assert allocation.debt_item_id == items[0].id
            assert allocation.credit_item_id == items[1].id
            assert allocation.amount == 300


async def test_credit_notes_claim_only_remaining_untaxed_original_supply(
    client, app, monkeypatch
):
    template = await invoice_command(client, app)
    transport = connection(client, app)
    original_input = dict(template.source_payload["invoice"])
    original_input["components"] = []
    original_input["accepted_calculation_hash"] = None
    original = await fresh_invoice(app, template, transport, kind="SALES", invoice=original_input)
    assert (await run(app, original)).outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            source = await db.scalar(select(InvoiceRecord).where(InvoiceRecord.kind == "SALES"))
            assert source is not None and source.commercial_total == 1000
            source_bill = await db.scalar(
                select(OpenItem).where(OpenItem.reference == original_input["bill_reference"])
            )
            cash = await db.scalar(select(Account).where(Account.kind == "CASH"))

    note_input = dict(original_input)
    note_input["source_invoice_id"] = str(source.id)
    note_input["party_line_key"] = str(uuid7())
    note_input["bill_reference"] = "CN-1"
    note_input["supplies"] = [dict(original_input["supplies"][0], amount="300")]
    note_input["accepted_calculation_hash"] = None
    note_input["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": str(source_bill.id)},
            "credit": {"line_key": note_input["party_line_key"]},
            "currency": "INR",
            "amount": "200",
        }
    ]
    note_input["tenders"] = [
        {
            "account_id": str(cash.id),
            "account_version": cash.row_version,
            "tender": {
                "tender_key": str(uuid7()),
                "line_key": str(uuid7()),
                "mode": "CASH",
                "amount": "100",
                "currency": "INR",
            },
        }
    ]
    wrong_target = dict(note_input)
    wrong_target["party_line_key"] = str(uuid7())
    wrong_target["bill_reference"] = "CN-WRONG"
    wrong_target["allocations"] = [
        dict(
            note_input["allocations"][0],
            debt={"item_id": str(uuid7())},
            credit={"line_key": wrong_target["party_line_key"]},
        )
    ]
    refused = await fresh_invoice(
        app, template, transport, kind="CREDIT_NOTE", invoice=wrong_target
    )
    assert (await run(app, refused)).outcome == "REJECTED"
    wrong_supply_kind = dict(note_input)
    wrong_supply_kind["party_line_key"] = str(uuid7())
    wrong_supply_kind["bill_reference"] = "CN-WRONG-KIND"
    wrong_supply_kind["supplies"] = [
        dict(note_input["supplies"][0], supply_kind="ACCOUNT")
    ]
    wrong_supply_kind["allocations"] = []
    wrong_supply_kind["tenders"] = []
    refused = await fresh_invoice(
        app, template, transport, kind="CREDIT_NOTE", invoice=wrong_supply_kind
    )
    assert (await run(app, refused)).outcome == "REJECTED"
    over_settled = dict(note_input)
    over_settled["party_line_key"] = str(uuid7())
    over_settled["bill_reference"] = "CN-OVERSETTLED"
    over_settled["allocations"] = [
        dict(note_input["allocations"][0], credit={"line_key": over_settled["party_line_key"]})
    ]
    over_settled["tenders"] = [
        dict(
            note_input["tenders"][0],
            tender=dict(note_input["tenders"][0]["tender"], amount="101"),
        )
    ]
    refused = await fresh_invoice(
        app, template, transport, kind="CREDIT_NOTE", invoice=over_settled
    )
    assert (await run(app, refused)).outcome == "REJECTED"
    first = await fresh_invoice(app, template, transport, kind="CREDIT_NOTE", invoice=note_input)
    committed = await run(app, first)
    assert committed.outcome == "COMMITTED", committed
    assert await run(app, first) == committed
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Allocation.id))) == 2
            assert (await db.scalar(select(BankInstrument))).amount == 100

    second_input = dict(note_input)
    second_input["party_line_key"] = str(uuid7())
    second_input["bill_reference"] = "CN-2"
    second_input["supplies"] = [dict(note_input["supplies"][0], amount="700")]
    second_input["allocations"] = []
    second_input["tenders"] = []
    second = await fresh_invoice(app, template, transport, kind="CREDIT_NOTE", invoice=second_input)
    second_result = await run(app, second)
    assert second_result.outcome == "COMMITTED", second_result

    over_input = dict(note_input)
    over_input["party_line_key"] = str(uuid7())
    over_input["bill_reference"] = "CN-3"
    over_input["supplies"] = [dict(note_input["supplies"][0], amount="1")]
    over_input["allocations"] = []
    over_input["tenders"] = []
    over = await fresh_invoice(app, template, transport, kind="CREDIT_NOTE", invoice=over_input)
    assert (await run(app, over)).outcome == "REJECTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            notes = list(
                await db.scalars(select(InvoiceRecord).where(InvoiceRecord.kind == "CREDIT_NOTE"))
            )
            assert len(notes) == 2
            assert {row.source_invoice_id for row in notes} == {source.id}
            assert {row.payable for row in notes} == {Decimal(300), Decimal(700)}
            settled_note_id = next(row.id for row in notes if row.payable == 300)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/src"))
    from reports.domain.reconcile import reconcile
    from reports.domain.statements import calculate
    from reports.schemas.requests import RunRequest

    from tests.test_invoice_reporting_flow import snapshot

    frozen, facts = await snapshot(client, app)
    reconcile(facts, frozen.control)
    rows, _ = calculate(
        facts,
        RunRequest(
            code="SALES_REGISTER",
            generation_id=uuid7(),
            date_from=dt.date(2026, 4, 1),
            date_to=dt.date(2026, 4, 30),
        ),
        frozen.control.coverage_start,
    )
    assert len(rows) == 3
    assert {row["direction"] for row in rows} == {"ORIGINAL", "REDUCTION"}
    assert {row["source_invoice_id"] for row in rows if row["direction"] == "REDUCTION"} == {
        str(source.id)
    }
    settlements, _ = calculate(
        facts,
        RunRequest(
            code="INVOICE_SETTLEMENT_REGISTER",
            generation_id=uuid7(),
            invoice_id=settled_note_id,
            date_from=dt.date(2026, 4, 1),
            date_to=dt.date(2026, 4, 30),
        ),
        frozen.control.coverage_start,
    )
    assert {row["settlement_amount"] for row in settlements} == {
        "100.0000",
        "200.0000",
    }


async def test_debit_note_reduces_untaxed_purchase_bill_with_original_source(
    client, app, monkeypatch
):
    template = await invoice_command(client, app, kind="PURCHASE")
    transport = connection(client, app)
    original_input = dict(template.source_payload["invoice"])
    original_input["components"] = []
    original_input["accepted_calculation_hash"] = None
    original = await fresh_invoice(
        app, template, transport, kind="PURCHASE", invoice=original_input
    )
    assert (await run(app, original)).outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            source = await db.scalar(select(InvoiceRecord).where(InvoiceRecord.kind == "PURCHASE"))
            assert source is not None and source.payable == 1000
            source_bill = await db.scalar(
                select(OpenItem).where(OpenItem.reference == original_input["bill_reference"])
            )

    note_input = dict(original_input)
    note_input["source_invoice_id"] = str(source.id)
    note_input["party_line_key"] = str(uuid7())
    note_input["bill_reference"] = "DN-1"
    note_input["supplies"] = [dict(original_input["supplies"][0], amount="250")]
    note_input["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": str(source_bill.id)},
            "credit": {"line_key": note_input["party_line_key"]},
            "currency": "INR",
            "amount": "250",
        }
    ]
    note = await fresh_invoice(app, template, transport, kind="DEBIT_NOTE", invoice=note_input)
    result = await run(app, note)
    assert result.outcome == "COMMITTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            record = await db.scalar(
                select(InvoiceRecord).where(InvoiceRecord.kind == "DEBIT_NOTE")
            )
            assert record.source_invoice_id == source.id and record.payable == 250
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/src"))
    from reports.domain.reconcile import reconcile
    from reports.domain.statements import calculate
    from reports.schemas.requests import RunRequest

    from tests.test_invoice_reporting_flow import snapshot

    frozen, facts = await snapshot(client, app)
    reconcile(facts, frozen.control)
    rows, _ = calculate(
        facts,
        RunRequest(
            code="PURCHASE_REGISTER",
            generation_id=uuid7(),
            date_from=dt.date(2026, 4, 1),
            date_to=dt.date(2026, 4, 30),
        ),
        frozen.control.coverage_start,
    )
    assert len(rows) == 2
    assert next(row for row in rows if row["direction"] == "REDUCTION")[
        "source_invoice_id"
    ] == str(source.id)


async def test_import_lookup_reports_note_entitlement_and_open_bill(client, app):
    from accounting.api.voucher_sources import (
        BillLookup,
        InvoiceLookup,
        open_bills,
        original_invoices,
    )

    template = await invoice_command(client, app)
    transport = connection(client, app)
    original_input = dict(template.source_payload["invoice"])
    original_input["components"] = []
    original_input["accepted_calculation_hash"] = None
    original = await fresh_invoice(app, template, transport, kind="SALES", invoice=original_input)
    assert (await run(app, original)).outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            record = await db.scalar(select(InvoiceRecord).where(InvoiceRecord.kind == "SALES"))
            item = await db.scalar(
                select(OpenItem).where(OpenItem.reference == record.bill_reference)
            )
    account, reference, company = record.party_account_id, record.bill_reference, record.company_id
    assert item is not None
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            found = await original_invoices(
                db, company, [InvoiceLookup(kind="SALES", party_account_id=account,
                                            bill_reference=reference)]
            )
            bills = await open_bills(db, company, [BillLookup(account_id=item.account_id,
                                                              reference=reference.lower())])
            other = await original_invoices(
                db, company, [InvoiceLookup(kind="PURCHASE", party_account_id=account,
                                            bill_reference=reference)]
            )
    assert other == []
    assert len(bills) == 1, bills
    assert len(found) == 1, (found, account, reference)
    assert found[0]["committed"] is True and found[0]["simple"] is True
    line = found[0]["lines"][0]
    assert line["commercial"] == line["remaining"] == "1000.0000"
    assert len(bills) == 1 and bills[0]["remaining"] == "1000.0000"
