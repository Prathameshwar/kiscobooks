"""Opening valuation is independent of optional purchase-reference pricing."""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from billing_platform.ids import uuid7

from catalog.schemas.simple_product_creation import SimpleBatchInput, SimpleCreationInput
from catalog.tasks import simple_batch_preparation
from catalog.tasks.simple_creation_preparation import creation_permissions
from catalog.tasks.simple_creation_steps import next_command


def test_batch_opening_cost_does_not_require_purchase_reference_permission():
    body = SimpleCreationInput(
        name="Goods",
        base_unit_id=uuid7(),
        batch_enabled=True,
        batches=[{"code": "LOT-1", "opening_quantity": "2", "opening_unit_cost": "7.50"}],
    )
    assert body.batches[0].opening_unit_cost == Decimal("7.50")
    assert body.batches[0].purchase_price is None
    assert "purchase_price.manage" not in creation_permissions(body)


def test_nonbatch_opening_can_value_stock_without_purchase_reference():
    body = SimpleCreationInput(
        name="Goods", base_unit_id=uuid7(), opening_quantity="2", opening_unit_cost="7.50"
    )
    assert body.opening_unit_cost == Decimal("7.50")
    assert body.purchase_price is None
    assert "purchase_price.manage" not in creation_permissions(body)


async def test_disabled_purchase_reference_still_allows_explicit_batch_opening_cost(monkeypatch):
    monkeypatch.setattr(
        simple_batch_preparation,
        "available",
        AsyncMock(
            return_value={
                "available": True,
                "required": False,
                "expiry_enabled": False,
                "expiry_required": False,
                "manufacture_date_required": False,
            }
        ),
    )
    monkeypatch.setattr(simple_batch_preparation, "effective", AsyncMock(return_value=None))
    monkeypatch.setattr(simple_batch_preparation, "sale_amounts", AsyncMock(return_value=[]))
    defaults = SimpleNamespace(
        configuration=SimpleNamespace(
            profiles=SimpleNamespace(inventory_template_revision_id=uuid7()),
            pricing=SimpleNamespace(purchase_reference_mode="DISABLED", mrp_mode="DISABLED"),
        ),
        product_type_revision_id=uuid7(),
        quantity=SimpleNamespace(quantity_decimal_places=0, quantity_increment=Decimal("1")),
        price=SimpleNamespace(price_decimal_places=2, price_increment=None),
    )
    body = SimpleCreationInput(
        name="Goods",
        base_unit_id=uuid7(),
        batch_enabled=True,
        batches=[{"code": "LOT-1", "opening_quantity": "2", "opening_unit_cost": "7.50"}],
    )
    access = SimpleNamespace(reference=AsyncMock(return_value=SimpleNamespace()))
    prepared = await simple_batch_preparation.prepare_batches(
        access,
        defaults,
        body,
        dt.date.today(),
        dt.date.today(),
    )
    assert prepared == [{"prices": []}]


def test_explicit_valuation_cost_and_reference_rate_remain_distinct():
    row = SimpleBatchInput(
        code="LOT-1", opening_quantity="2", opening_unit_cost="7.50", purchase_price="9.00"
    )
    assert row.opening_unit_cost == Decimal("7.50")
    assert row.purchase_price == Decimal("9.00")


async def test_native_opening_values_stock_using_cost_instead_of_reference_rate():
    company, creation, item, unit, revision, warehouse, lot = (uuid7() for _ in range(7))
    request = SimpleCreationInput(
        name="Goods",
        base_unit_id=unit,
        batch_enabled=True,
        batches=[
            {
                "code": "LOT-1",
                "opening_quantity": "2",
                "opening_unit_cost": "7.50",
                "purchase_price": "9",
            }
        ],
    )
    calls = []

    async def call(service, method, path, body=None):
        calls.append((service, path, body))
        if service == "catalog":
            return {"units": [{"usage_role": "BASE", "revision_id": str(revision)}]}
        assert Decimal(body["opening"]["unit_cost"]) == Decimal("7.50")
        return {"base_quantity": "2", "received_value": "15.00"}

    result = await next_command(
        SimpleNamespace(call=call),
        company,
        creation,
        "OPENING",
        request,
        {
            "opening_date": "2026-11-07",
            "warehouse_id": str(warehouse),
            "batch_ids": [str(lot)],
            "currency": "INR",
        },
        item,
    )
    assert result["body"]["lines"][0]["received_value"] == "15.00"
    assert Decimal(result["body"]["lines"][0]["opening"]["unit_cost"]) == Decimal("7.50")
