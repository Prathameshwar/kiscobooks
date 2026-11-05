"""Physical batch MRP has native field authority and an immutable declaration."""

from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.api import stock_tracking as api
from accounting.models.stock_tracking import StockLot
from tests.conftest import TENANT
from tests.test_masters import prepare
from tests.test_stock_tracking import BASE, auth, batch, facts


async def test_initial_batch_mrp_is_exact_authorized_and_immutable(client, app, monkeypatch):
    await prepare(client)
    unit = uuid7()

    async def source(request, current, item, **kwargs):
        return facts(current.context.company_id, item, base_unit_id=unit)

    monkeypatch.setattr(api, "source", source)
    body = batch(mrp_amount="99.9500", mrp_currency="INR", mrp_unit_id=str(unit))
    wrong = await client.post(
        BASE + "/batches", headers=auth(), json=body | {"mrp_unit_id": str(uuid7())}
    )
    assert wrong.status_code == 422, wrong.text
    headers = auth()
    response = await client.post(BASE + "/batches", headers=headers, json=body)
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["mrp_amount"]) == Decimal("99.95")
    assert (await client.post(BASE + "/batches", headers=headers, json=body)).json()[
        "id"
    ] == response.json()["id"]
    changed = await client.patch(
        BASE + "/batches/" + response.json()["id"],
        headers=auth(),
        json={
            "expected_version": 1,
            "mrp_amount": "150",
            "reason": "Attempt to rewrite physical MRP",
        },
    )
    assert changed.status_code == 422
    with tenant_scope(TENANT):
        with pytest.raises(ConflictError):
            async with app.state.session_factory.begin() as db:
                lot = await db.scalar(select(StockLot))
                lot.mrp_amount = Decimal("150")
