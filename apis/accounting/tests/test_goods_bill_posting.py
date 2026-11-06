"""B24 phase 2: a goods Purchase bill posts its stock and its invoice in one execution.

The worked example from the owner decision (2026-11-03): 10 x 100 and 5 x 100 with 150
freight, 18% intra-state GST, the second line's GST not claimable. Stock comes in at 1,100
and 649; the journal debits inventory by the same amounts and input GST by 198; the supplier
is credited 1,947 as a new bill to pay.
"""

import datetime as dt
import hashlib
from decimal import Decimal

import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.stock_facts import StockFenceFacts
from voucher_execution.transport import command_digest

from accounting.models.invoice import InvoiceRecord
from accounting.models.ledger import Journal, JournalLine
from accounting.models.stock import StockBalance, StockPosting
from accounting.models.subledger import OpenItem
from tests.conftest import SECRET, TENANT
from tests.test_goods_invoice_calculation import (
    DAY,
    bill,
    calculated,
    freight,
    goods_line,
    goods_world,
)
from tests.test_ledger_api import LEDGER_PERMISSIONS, ledger_headers
from tests.test_stock_effects import Source
from tests.test_voucher_execution import command
from tests.test_voucher_tax import MH

POLICY = {"manual_discounts_allowed": True, "charges_allowed": True}


def poster(*, reverse=False):
    headers = ledger_headers(
        permissions=LEDGER_PERMISSIONS
        | {"vouchers.post", "vouchers.read", "accounting.stock.post", "accounting.stock.read"}
        | ({"vouchers.reverse", "accounting.stock.reverse"} if reverse else set()),
        features={"inventory"},
        registrations=[MH],
    )
    context = verify_company_context(
        headers["X-Company-Context"], headers["X-Company-Signature"], SECRET.encode()
    )
    body, signature = sign_company_context(
        context.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return DelegatedAuthority(
        actor_context=headers["X-Actor-Context"],
        actor_signature=headers["X-Actor-Signature"],
        company_context=body,
        company_signature=signature,
    )


async def accepted_bill(client, app, monkeypatch):
    w = await goods_world(client, app, monkeypatch, finalize_zero=True)
    w["authority"] = poster()
    milk = goods_line(w["milk"], w["location"], "10", "100", w["inventory"])
    ghee = goods_line(
        w["ghee"],
        w["location"],
        "5",
        "100",
        w["inventory"],
        input_credit="INELIGIBLE",
        input_credit_reason="Used for the staff canteen",
    )
    evidence = {
        "kind": "PURCHASE",
        "profile": "STANDARD",
        "company_configuration_hash": "a" * 64,
        "policy": {"invoice": POLICY, "financial": {}},
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    preview = bill(
        w, [milk, ghee], components=[freight([milk[0]["line_key"], ghee[0]["line_key"]])]
    ).model_copy(update={"configuration_hash": digest})
    result = await calculated(client, app, preview)
    invoice = preview.invoice.model_copy(
        update={"accepted_calculation_hash": result.calculation_hash}
    )
    payload = {
        "mode": "ITEMS",
        "currency": "INR",
        "document_date": DAY,
        "posting_date": DAY,
        "stock_date": DAY,
        "narration": "Supplier bill SUP-GOODS-1",
        "invoice": invoice.model_dump(mode="json"),
        "stock": preview.stock.model_dump(mode="json"),
        "lines": [
            {
                "line_key": stock["line_id"],
                "item": {
                    "item_id": stock["item_id"],
                    "item_version": 1,
                    "unit_id": str(w["catalog"][preview.stock.lines[index].item_id].base_unit_id),
                    "actual_quantity": stock["quantity"],
                    "billed_quantity": stock["quantity"],
                },
            }
            for index, stock in enumerate(
                [line.model_dump(mode="json") for line in preview.stock.lines]
            )
        ],
    }
    request = command(
        w["data"]["period"],
        protocol_version=2,
        kind="PURCHASE",
        posting_date=dt.date.fromisoformat(DAY),
        stock_date=dt.date.fromisoformat(DAY),
        source_payload=payload,
        content_hash=hashlib.sha256(canonical_json(payload)).hexdigest(),
        configuration_hash=digest,
        configuration_evidence=evidence | {"digest": digest},
        authority=w["authority"],
    )
    request = request.model_copy(update={"request_hash": command_digest(request)})
    now = utcnow()
    facts = StockFenceFacts(
        tenant_id=request.tenant_id,
        company_id=request.company_id,
        execution_id=request.execution_id,
        actor_user_id=request.actor_user_id,
        fence_id=uuid7(),
        stock_date=request.stock_date,
        issued_at=now,
        expires_at=now + dt.timedelta(seconds=60),
        policy_generation=1,
        source_version=1,
        content_hash=request.content_hash,
        items=(w["milk"], w["ghee"]),
        warehouses=(w["location"],),
        bins=(),
    )
    return w, request, Source(facts), milk, ghee


async def test_a_goods_bill_posts_landed_stock_input_gst_and_the_supplier_bill_once(
    client, app, monkeypatch
):
    from accounting.tasks.stock_execution import _dispatch, dispatch

    w, request, remote, milk, ghee = await accepted_bill(client, app, monkeypatch)
    owner = w["data"]["authority"]
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=remote,
        enabled=True,
    )
    assert result.outcome == "COMMITTED", result
    assert {effect.effect_kind for effect in result.effects} >= {"STOCK", "JOURNAL"}
    replay = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=None,
        enabled=True,
    )
    assert replay == result
    inventory = w["inventory"].id
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            posting = await db.scalar(select(StockPosting))
            assert posting.action == "PURCHASE_INVOICE"
            balances = sorted(
                (row.quantity for row in await db.scalars(select(StockBalance))), key=Decimal
            )
            assert balances == [Decimal("5"), Decimal("10")]
            journal = await db.scalar(select(Journal).where(Journal.status == "POSTED"))
            assert journal is not None
            lines = list(
                await db.scalars(select(JournalLine).where(JournalLine.journal_id == journal.id))
            )
            debits = sorted(
                row.amount for row in lines if row.account_id == inventory and row.side == "DEBIT"
            )
            assert debits == [Decimal("649"), Decimal("1100")]
            supplier = [row for row in lines if str(row.account_id) == w["supplier"]["id"]]
            assert [(row.side, row.amount) for row in supplier] == [("CREDIT", Decimal("1947"))]
            assert sum(row.amount for row in lines if row.side == "DEBIT") == Decimal("1947")
            assert isinstance(debits[0], Decimal)
            item = await db.scalar(
                select(OpenItem).where(OpenItem.journal_line_id == supplier[0].id)
            )
            assert item is not None and item.amount == Decimal("1947")
            assert await db.scalar(select(func.count(InvoiceRecord.id))) == 1
            assert await db.scalar(select(func.count(StockPosting.id))) == 1


async def test_unconsumed_goods_purchase_reverses_stock_and_supplier_bill(client, app, monkeypatch):
    from accounting.tasks.stock_execution import _dispatch

    w, request, remote, *_ = await accepted_bill(client, app, monkeypatch)
    owner = w["data"]["authority"]
    posted, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=remote,
        enabled=True,
    )
    assert posted.outcome == "COMMITTED", posted
    reverse = request.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": request.execution_id,
            "correction_reason": "Correct supplier goods bill",
            "posting_date": dt.date(2026, 4, 11),
            "stock_date": dt.date(2026, 4, 11),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "authority": poster(reverse=True),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    now = utcnow()
    proof = remote.facts.model_copy(
        update={
            "action": "REVERSE",
            "execution_id": reverse.execution_id,
            "fence_id": uuid7(),
            "stock_date": reverse.stock_date,
            "issued_at": now,
            "expires_at": now + dt.timedelta(seconds=60),
        }
    )
    reversed_result, _ = await _dispatch(
        app.state.session_factory,
        reverse,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(proof),
        enabled=True,
    )
    assert reversed_result.outcome == "COMMITTED", reversed_result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert sorted(await db.scalars(select(StockBalance.quantity))) == [Decimal(0), Decimal(0)]
            assert await db.scalar(select(func.count(StockPosting.id))) == 2
            assert await db.scalar(select(func.count(InvoiceRecord.id))) == 1


async def test_a_goods_bill_is_refused_while_the_invoice_release_is_off_and_leaves_nothing(
    client, app, monkeypatch
):
    from accounting.tasks.stock_execution import dispatch

    w, request, remote, *_ = await accepted_bill(client, app, monkeypatch)
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=w["data"]["authority"],
        source_client=remote,
        enabled=False,
    )
    assert result.outcome == "REJECTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 0
            assert await db.scalar(select(func.count(InvoiceRecord.id))) == 0


@pytest.mark.parametrize("change", ["hash", "price"])
async def test_a_changed_or_unaccepted_bill_never_posts(client, app, monkeypatch, change):
    from accounting.tasks.stock_execution import dispatch

    w, request, remote, *_ = await accepted_bill(client, app, monkeypatch)
    payload = dict(request.source_payload)
    invoice = dict(payload["invoice"])
    if change == "hash":
        invoice["accepted_calculation_hash"] = "c" * 64
    else:
        invoice["supplies"] = [
            dict(invoice["supplies"][0], amount="1100.0000", unit_price="110.0000"),
            *invoice["supplies"][1:],
        ]
    payload["invoice"] = invoice
    changed = request.model_copy(
        update={
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
        }
    )
    changed = changed.model_copy(update={"request_hash": command_digest(changed)})
    remote.facts = remote.facts.model_copy(update={"content_hash": changed.content_hash})
    result = await dispatch(
        app.state.session_factory,
        changed,
        secret=SECRET.encode(),
        client=w["data"]["authority"],
        source_client=remote,
        enabled=True,
    )
    assert result.outcome == "REJECTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 0
