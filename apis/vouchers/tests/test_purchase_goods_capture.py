"""B24: a Product or Mixed Purchase bill is saved with its stock lines, calculated by Accounting
with them, accepted, submitted and posted as one stock-and-invoice execution."""

import pytest
from billing_platform.ids import uuid7
from conftest import headers
from test_foundation import create_type
from test_invoice_capture import invoice_body
from test_purchase_lifecycle_integrity import (
    CALCULATION,
    TODAY,
    master,
    owner,
    path,
    project,
    request_for,
    seed,
)
from unit_source_factories import unit_masters


def stocked():
    """A company that tracks inventory: goods bills move stock."""
    return headers(features=frozenset({"inventory"}))


async def accept(client, prefix, document):
    return await client.post(
        path(prefix, document, "/invoice-acceptance"),
        json={"expected_version": document["row_version"], "calculation_hash": CALCULATION},
        headers=stocked(),
    )


async def submit(client, prefix, document):
    return await client.post(
        path(prefix, document, "/submit"),
        json={"expected_version": document["row_version"]},
        headers=stocked(),
    )


PRODUCT_TYPE = {
    "schema_version": 2,
    "invoice": {"allowed_supply_kinds": ["GOODS", "SERVICE", "ACCOUNT"]},
    "default_mode": "ITEMS",
    "allowed_modes": ["ITEMS", "MIXED"],
    "approval_required": False,
}


async def goods_bill(client, prefix, app, *, mixed=False, stock=True, **stock_changes):
    item, unit, line, warehouse = uuid7(), uuid7(), uuid7(), uuid7()
    supplier = uuid7()
    kind = await create_type(client, prefix, kind="PURCHASE", policy=PRODUCT_TYPE)
    body = invoice_body()
    body["components"] = []
    body["tax"] = {"profile": "UNTAXED_ACCOUNT"}
    body["supplies"][0].update(
        line_key=str(line),
        supply_kind="GOODS",
        item_line_key=str(line),
        description="Milk powder 1kg",
        amount="1000",
        unit_price="100",
        quantities=[
            {"basis": "ACTUAL", "quantity": "10", "unit_id": str(unit)},
            {"basis": "BILLED", "quantity": "10", "unit_id": str(unit)},
        ],
    )
    if mixed:
        body["supplies"].append(
            body["supplies"][0]
            | {
                "line_key": str(uuid7()),
                "supply_kind": "SERVICE",
                "item_line_key": None,
                "description": "Unloading",
                "amount": "50",
                "unit_price": None,
                "quantities": [],
            }
        )
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    await project(
        app,
        [
            *unit_masters(item, unit),
            master(
                "item_transaction_policy",
                item,
                kind="GOODS",
                inventory_mode="STOCK",
                item_version=1,
                sellable=True,
                purchasable=True,
            ),
        ],
        "catalog",
    )
    changes = {
        "mode": "MIXED" if mixed else "ITEMS",
        "stock_date": TODAY,
        "lines": [
            {
                "line_key": str(line),
                "item": {
                    "item_id": str(item),
                    "item_version": 1,
                    "unit_id": str(unit),
                    "actual_quantity": "10",
                    "billed_quantity": "10",
                },
            }
        ],
    }
    if stock:
        changes["stock"] = {
            "action": "PURCHASE_INVOICE",
            "stock_date": TODAY,
            "currency": "INR",
            "reason": "Supplier bill INV-1",
            "lines": [
                {
                    "line_id": str(line),
                    "item_id": str(item),
                    "warehouse_id": str(warehouse),
                    "quantity": "10",
                }
            ],
        } | stock_changes
    request = request_for(kind, body, supplier, **changes)
    return await client.post(prefix + "/vouchers", json=request, headers=stocked()), request


@pytest.mark.parametrize("mixed", [False, True], ids=["product", "mixed"])
async def test_a_goods_bill_is_saved_calculated_with_its_stock_lines_and_accepted(
    client, prefix, app, monkeypatch, mixed
):
    created, request = await goods_bill(client, prefix, app, mixed=mixed)
    assert created.status_code == 201, created.text
    document = created.json()
    calls = owner(app, monkeypatch)
    preview = await client.post(
        path(prefix, document, "/invoice-preview"),
        json={"expected_version": document["row_version"]},
        headers=stocked(),
    )
    assert preview.status_code == 200, preview.text
    sent = calls[-1]
    assert sent.stock is not None and sent.stock.action == "PURCHASE_INVOICE"
    assert [str(line.line_id) for line in sent.stock.lines] == [
        line["line_id"] for line in request["stock"]["lines"]
    ]
    accepted = await accept(client, prefix, document)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["invoice"]["accepted_calculation_hash"] == CALCULATION
    reopened = await client.get(path(prefix, document), headers=stocked())
    assert reopened.json()["stock"]["action"] == "PURCHASE_INVOICE"
    submitted = await submit(client, prefix, accepted.json())
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "APPROVED"


async def test_the_bill_bills_what_it_receives_on_its_posting_date(client, prefix, app):
    created, _ = await goods_bill(client, prefix, app, stock_date="2001-01-01")
    assert created.status_code == 422, created.text


async def test_a_goods_bill_without_its_stock_lines_is_still_the_old_refusal(
    client, prefix, app, monkeypatch
):
    created, _ = await goods_bill(client, prefix, app, stock=False)
    assert created.status_code == 201, created.text
    owner(app, monkeypatch)
    refused = await accept(client, prefix, created.json())
    assert refused.status_code in {409, 422}, refused.text
    assert "Goods and mixed purchases" in refused.json()["error"]["message"]


async def test_an_account_purchase_type_cannot_take_goods(client, prefix, app):
    other = await create_type(
        client,
        prefix,
        code="PUR_ACC_ONLY2",
        kind="PURCHASE",
        policy={
            "schema_version": 2,
            "invoice": {"allowed_supply_kinds": ["ACCOUNT"]},
            "default_mode": "ITEMS",
            "allowed_modes": ["ITEMS"],
        },
    )
    _, request = await goods_bill(client, prefix, app)
    request["type_revision_id"] = other["revision_id"]
    refused = await client.post(prefix + "/vouchers", json=request, headers=stocked())
    assert refused.status_code == 422, refused.text
    assert "does not take goods" in refused.text or "not configured" in refused.text


async def posted_bill(client, prefix, app, monkeypatch):
    import datetime as dt
    import uuid

    from billing_platform.db import tenant_scope
    from conftest import COMPANY, TENANT
    from test_money_posting import authority_headers

    from vouchers.models import core as m
    from vouchers.schemas.sources import SourceBundle
    from vouchers.tasks.sources import apply_bundle

    created, _ = await goods_bill(client, prefix, app)
    document = created.json()
    owner(app, monkeypatch)
    accepted = await accept(client, prefix, document)
    submitted = await submit(client, prefix, accepted.json())
    assert submitted.status_code == 200, submitted.text
    day = dt.date.today().isoformat()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "source_id": str(uuid7()),
                        "entity_type": "fiscal_period",
                        "source_version": 1,
                        "status": "ACTIVE",
                        "facts": {"start_date": day, "end_date": day},
                    }
                ],
            }
        ),
        "accounting",
    )

    async def post():
        return await client.post(
            path(prefix, document, "/post"),
            json={"expected_version": submitted.json()["row_version"]},
            headers=authority_headers(features=frozenset({"inventory"})),
        )

    def operation(result):
        async def read():
            with tenant_scope(TENANT):
                async with app.state.session_factory() as db:
                    return await db.get(
                        m.VoucherOperation, uuid.UUID(result.json()["operation_id"])
                    )

        return read()

    return post, operation


async def test_a_goods_bill_posts_stock_and_invoice_together_only_when_both_are_released(
    client, prefix, app, monkeypatch
):
    post, operation = await posted_bill(client, prefix, app, monkeypatch)
    app.state.settings.stock_execution_enabled = True
    app.state.settings.invoice_execution_enabled = False
    refused = await post()
    assert refused.status_code == 409, refused.text
    app.state.settings.invoice_execution_enabled = True
    app.state.settings.stock_execution_enabled = False
    refused = await post()
    assert refused.status_code == 409, refused.text
    app.state.settings.stock_execution_enabled = True
    result = await post()
    assert result.status_code == 202, result.text
    row = await operation(result)
    payload = row.command["source_payload"]
    assert row.command["kind"] == "PURCHASE" and row.command.get("voucher_number") is None
    assert payload["stock"]["action"] == "PURCHASE_INVOICE"
    assert payload["invoice"]["accepted_calculation_hash"] == CALCULATION
