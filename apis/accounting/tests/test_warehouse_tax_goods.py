"""Receiving warehouse tax facts constrain and survive native goods tax calculation."""

import uuid

import pytest
from billing_platform.ids import uuid7

from accounting.tasks import invoice_goods
from tests.test_goods_invoice_calculation import bill, calculated, goods_line, goods_world, refused
from tests.test_voucher_tax import MH


@pytest.mark.parametrize("mismatch", [False, True])
async def test_goods_receiving_warehouse_registration_is_validated_and_retained(
    client, app, monkeypatch, mismatch
):
    world = await goods_world(client, app, monkeypatch)
    acquire = invoice_goods.acquire
    warehouse = world["location"].model_copy(
        update={
            "tax_registration_id": uuid7() if mismatch else uuid.UUID(MH["id"]),
            "country_code": "IN",
            "state_code": "IN-MH",
            "address_line1": "Receiving warehouse address",
        }
    )

    async def warehouse_facts(settings, command, *, labels=False):
        facts = await acquire(settings, command, labels=labels)
        return invoice_goods.GoodsFacts(
            facts.lines, facts.items, {warehouse.warehouse_id: warehouse}
        )

    monkeypatch.setattr(invoice_goods, "acquire", warehouse_facts)
    supply = goods_line(world["milk"], world["location"], "1", "100", world["inventory"])
    command = bill(world, [supply])
    if mismatch:
        response = await refused(client, app, command)
        assert response.status_code == 422, response.text
        assert "receiving warehouse" in response.text
    else:
        result = await calculated(client, app, command)
        context = result.tax_evidence[0]["receiving_warehouse"]
        assert context["tax_registration_id"] == MH["id"]
        assert context["state_code"] == "IN-MH"
        assert context["address_line1"] == "Receiving warehouse address"
