"""Physical evidence reads obey company and contributing-field authority."""

from decimal import Decimal

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7

from tests.conftest import COMPANY, TENANT, headers
from tests.test_stock_ledger import item, ledger, line, warehouse

BASE = f"/v1/companies/{COMPANY}/stock"


def auth(**changes):
    return headers(permissions={"accounting.stock.read"}, features={"inventory"}, **changes)


async def seed(app):
    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            movement = await owner.receive(
                line(product, location, 2), product, location, value=Decimal("12.50")
            )
            return product, location, movement


async def test_stock_reads_lean_pages_details_filters_and_wrong_company(client, app):
    product, location, movement = await seed(app)
    assert (await client.get(BASE + "/positions")).status_code == 401
    assert (await client.get(BASE + "/positions", headers=headers())).status_code == 403
    positions = await client.get(
        BASE + "/positions", params={"item_id": str(product.item_id)}, headers=auth()
    )
    assert positions.status_code == 200, positions.text
    row = positions.json()["items"][0]
    assert row["quantity"] == "2.0000" and "created_at" not in row
    details = await client.get(BASE + "/positions/" + row["id"], headers=auth())
    assert details.status_code == 200 and "created_at" in details.json()
    movements = await client.get(BASE + "/movements", headers=auth())
    assert movements.status_code == 200, movements.text
    evidence = movements.json()["items"][0]
    assert evidence["value"] == "12.5000" and evidence["currency"] == "INR"
    assert evidence["item_id"] == str(product.item_id) and evidence["id"] == str(
        movement.movement_id
    )
    other = uuid7()
    denied = await client.get(
        BASE.replace(str(COMPANY), str(other)) + "/positions/" + row["id"],
        headers=auth(company=other),
    )
    assert denied.status_code == 403, denied.text
    configuration = await client.get(BASE + "/configuration", headers=auth())
    assert configuration.status_code == 200 and configuration.json()["posting_enabled"] is False
    assert configuration.json()["can_configure"] is False
    assert (
        await client.get(BASE + "/movements", params={"sort": "value"}, headers=auth())
    ).status_code == 422


async def test_stock_reads_mask_contributing_fields_and_forbid_filtering_hidden_values(client, app):
    product, location, movement = await seed(app)

    def deny(entity, field):
        return {
            "entity_type": "accounting." + entity,
            "field_key": field,
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }

    key = auth(policies=[deny("stock_position", "warehouse_id"), deny("stock_posting", "currency")])
    result = await client.get(BASE + "/movements", headers=key)
    assert result.status_code == 200, result.text
    row = result.json()["items"][0]
    assert "warehouse_id" not in row and "currency" not in row and "value" not in row
    detail = await client.get(BASE + "/movements/" + str(movement.movement_id), headers=key)
    assert detail.status_code == 200 and "value" not in detail.json()
    refused = await client.get(
        BASE + "/movements", params={"warehouse_id": str(location.warehouse_id)}, headers=key
    )
    assert refused.status_code == 403, refused.text
    receipt = await client.get(
        BASE + "/movements", headers=auth(policies=[deny("stock_movement", "received_value")])
    )
    assert receipt.status_code == 200 and "value" not in receipt.json()["items"][0]
    invalid = await client.get(
        BASE + "/positions", params={"voucher_id": str(uuid7())}, headers=auth()
    )
    assert invalid.status_code == 422, invalid.text
