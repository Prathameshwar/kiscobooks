"""S09: native unit admission rejects fractional grid errors before receipts exist."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.models.units import UnitOfMeasure
from tests.test_simple_product_creation import starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_simple_quantity_grid_is_enforced_before_admission(
    client, factory, tenant_a, monkeypatch
):
    # Control owner readiness only; exercise real native configuration and admission.
    monkeypatch.setattr(
        "catalog.tasks.simple_product_creation.opening_preflight", AsyncMock(return_value={})
    )
    root, auth, unit = await starter(factory, tenant_a, inventory=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            measure = await db.get(UnitOfMeasure, uuid.UUID(unit))
            assert measure is not None
            measure.decimal_places = 3
            measure.quantity_increment = Decimal("0.005")
    body = {
        "name": "S09 exact opening",
        "base_unit_id": unit,
        "opening_quantity": "12.346",
        "opening_unit_cost": "42.5",
        "purchase_price": "45",
    }
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert response.status_code == 422, response.text
    assert "opening_quantity" in response.json()["error"]["fields"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(SimpleProductCreation.id))) == 0
    body["opening_quantity"] = "12.345"
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert response.status_code == 201, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            receipt = (await db.scalars(select(SimpleProductCreation))).one()
            assert Decimal(receipt.request["opening_quantity"]) == Decimal("12.345")
            assert Decimal(receipt.request["opening_unit_cost"]) == Decimal("42.5")
            assert Decimal("12.345") * Decimal("42.5") == Decimal("524.6625")
