"""A goods Purchase bill prints its HSN and unit labels (designer plan §8 R1, 2026-11-04).

HSN comes from what the line was taxed under: the calculation's tax evidence for a preview,
the posted supply fact for a posted bill. A unit label comes only from Catalog's own facts,
read with the actor's rights; a posted bill whose product can no longer be read still prints.
"""

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from sqlalchemy import select
from voucher_execution.invoice import InvoicePreviewCommand
from voucher_execution.printing import PurchasePrintCommand

from accounting.models.invoice import InvoiceSupplyFact
from accounting.tasks import invoice_goods
from tests.conftest import SECRET, TENANT
from tests.test_goods_bill_posting import POLICY, accepted_bill
from tests.test_goods_invoice_calculation import DAY, bill, goods_line, goods_world
from tests.test_invoice_preview import connection


async def test_a_goods_preview_prints_each_lines_hsn_and_unit_label(client, app, monkeypatch):
    w = await goods_world(client, app, monkeypatch)
    milk = goods_line(w["milk"], w["location"], "10", "100", w["inventory"])
    command = bill(w, [milk])
    facts = await connection(client, app).purchase_print(
        PurchasePrintCommand(preview=command, revision_id=command.tenant_id, require_posted=False)
    )
    assert facts.source == "PREVIEW"
    assert [(row.classification_code, row.unit_label) for row in facts.lines] == [("0402", "kg")]
    assert str(facts.lines[0].key) == milk[0]["line_key"]


async def test_a_goods_preview_is_refused_when_its_product_facts_cannot_be_read(
    client, app, monkeypatch
):
    w = await goods_world(client, app, monkeypatch)
    command = bill(w, [goods_line(w["milk"], w["location"], "1", "100", w["inventory"])])

    async def unavailable(settings, command, *, labels=False):
        raise ConflictError("activate the product before billing it")

    monkeypatch.setattr(invoice_goods, "acquire", unavailable)
    with pytest.raises(httpx.HTTPStatusError) as error:
        await connection(client, app).purchase_print(
            PurchasePrintCommand(
                preview=command, revision_id=command.tenant_id, require_posted=False
            )
        )
    assert error.value.response.status_code == 409


async def posted_bill(client, app, monkeypatch):
    from accounting.tasks.stock_execution import _dispatch

    w, request, remote, milk, ghee = await accepted_bill(client, app, monkeypatch)
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=w["data"]["authority"],
        source_client=remote,
        enabled=True,
    )
    assert result.outcome == "COMMITTED", result
    # The print command Vouchers sends for this saved bill: its invoice and its stock lines.
    source = request.source_payload
    preview = InvoicePreviewCommand.model_validate(
        {
            "tenant_id": request.tenant_id,
            "company_id": request.company_id,
            "actor_user_id": request.actor_user_id,
            "authority": w["authority"],
            "kind": "PURCHASE",
            "currency": "INR",
            "document_date": DAY,
            "posting_date": DAY,
            "configuration_hash": request.configuration_hash,
            "company_configuration_hash": w["company"].finance.configuration_hash,
            "policy": POLICY,
            "invoice": source["invoice"],
            "stock": source["stock"],
        }
    )
    command = PurchasePrintCommand(
        preview=preview, revision_id=request.revision_id, require_posted=True
    )
    return command, milk, ghee


async def test_a_posted_goods_bill_records_and_prints_the_hsn_it_was_taxed_under(
    client, app, monkeypatch
):
    command, milk, ghee = await posted_bill(client, app, monkeypatch)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            codes = {row.classification_code for row in await db.scalars(select(InvoiceSupplyFact))}
    # Goods evidence names its HSN under "hsn"; the posted fact recorded none before this fix.
    assert codes == {"0402"}
    facts = await connection(client, app).purchase_print(command)
    assert facts.source == "POSTED"
    printed = {str(row.key): (row.classification_code, row.unit_label) for row in facts.lines}
    assert printed == {
        milk[0]["line_key"]: ("0402", "kg"),
        ghee[0]["line_key"]: ("0402", "kg"),
    }


async def test_a_posted_goods_bill_still_prints_when_its_product_can_no_longer_be_read(
    client, app, monkeypatch
):
    command, *_ = await posted_bill(client, app, monkeypatch)

    async def withdrawn(settings, command, *, labels=False):
        raise ConflictError("stock requires activated goods and their active native base unit")

    monkeypatch.setattr(invoice_goods, "acquire", withdrawn)
    facts = await connection(client, app).purchase_print(command)
    assert facts.source == "POSTED"
    assert {(row.classification_code, row.unit_label) for row in facts.lines} == {("0402", None)}
