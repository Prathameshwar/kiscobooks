"""The Catalog coordinator's exact opening command uses the native voucher lifecycle."""

import uuid
from pathlib import Path

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT
from test_foundation import create_type
from test_money_posting import authority_headers
from test_stock_opening_import import document

from vouchers.models.core import VoucherOperation
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle


async def test_simple_opening_is_submitted_numbered_and_admitted_without_approval(
    client, prefix, app, monkeypatch
):
    # Import only the coordinator/schema (no Catalog ORM) to verify its actual wire contract.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "catalog/src"))
    from catalog.schemas.simple_product_creation import SimpleCreationInput
    from catalog.tasks.simple_creation_steps import next_command

    prepared = (await document(client, prefix, app, count=1))["document"]["vouchers"][0]
    kind = await create_type(
        client,
        prefix,
        code="SIMPLE_OPEN",
        kind="STOCK_JOURNAL",
        profile="OPENING",
        policy={
            "schema_version": 2,
            "stock": {},
            "default_mode": "ITEMS",
            "allowed_modes": ["ITEMS"],
            "approval_required": False,
            "self_approval_allowed": False,
        },
    )
    item = prepared["lines"][0]["item"]
    entry = prepared["stock"]["lines"][0]
    entry.pop("unit_ids")
    entry.update(quantity="3", received_value="37.50")
    entry["opening"].update(
        entered_quantity="3", cost_mode="RATE", unit_cost="12.50", priced_quantity="1"
    )
    progress = {
        "type_revision_id": kind["revision_id"],
        "control_id": prepared["stock"]["opening_control_id"],
        "opening_date": prepared["stock_date"],
        "currency": "INR",
        "manifest": {
            "stock_date": prepared["stock_date"],
            "currency": "INR",
            "opening_mode": "COMBINED",
            "lines": [entry],
            "reason": "Opening stock entered with product creation",
        },
    }
    product = SimpleCreationInput(
        name="Opening product",
        base_unit_id=item["unit_id"],
        purchase_price="12.50",
        opening_quantity="3",
    )
    signed = authority_headers(features=frozenset({"inventory"}))

    class Owners:
        async def call(self, service, method, path, body=None, key=None):
            if service == "catalog":
                return {"item_version": item["item_version"]}
            response = await client.request(method, path, headers=signed, json=body)
            assert response.status_code == 200, response.text
            return response.json()

    for step in ("VOUCHER", "SUBMIT", "ISSUE"):
        command = await next_command(
            Owners(), COMPANY, uuid7(), step, product, progress, uuid.UUID(item["item_id"])
        )
        response = await client.post(
            command["path"],
            json=command["body"],
            headers=authority_headers(features=frozenset({"inventory"})),
        )
        assert response.status_code in {200, 201}, response.text
        row = response.json()
        progress["voucher_id"] = row["id"]
        assert row["status"] == {"VOUCHER": "DRAFT", "SUBMIT": "APPROVED", "ISSUE": "ISSUED"}[step]
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
                        "facts": {
                            "start_date": prepared["posting_date"],
                            "end_date": prepared["posting_date"],
                        },
                    }
                ],
            }
        ),
        "accounting",
    )
    app.state.settings.stock_execution_enabled = True
    command = await next_command(
        Owners(), COMPANY, uuid7(), "POST", product, progress, uuid.UUID(item["item_id"])
    )
    response = await client.post(
        command["path"],
        json=command["body"],
        headers=authority_headers(features=frozenset({"inventory"})),
    )
    assert response.status_code == 202, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            operation = await db.get(VoucherOperation, uuid.UUID(response.json()["operation_id"]))
            assert operation.command["voucher_number"]
            stock = operation.command["source_payload"]["stock"]
            assert stock["lines"][0]["received_value"] == "37.5000"
            assert stock["lines"][0]["opening"]["unit_cost"] == "12.5000"
