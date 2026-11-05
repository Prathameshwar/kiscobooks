"""Counted zero and native observation references survive immutable voucher revisions."""

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from conftest import TENANT
from sqlalchemy import select
from test_stock_capture import auth, fixture

from vouchers.models.stock import VoucherStockDetail


async def test_count_zero_persists_and_cannot_masquerade_as_receipt(client, prefix, app):
    body = await fixture(client, prefix, app, kind_code="PHYSICAL_STOCK")
    body["lines"][0]["item"]["actual_quantity"] = "0"
    stock_line = body["stock"]["lines"][0]
    stock_line.pop("received_value")
    stock_line["unit_ids"] = []
    stock_line["quantity"] = "0"
    stock_line["count"] = {"observation_id": str(uuid7()), "expected_revision": 2}
    body["stock"]["action"] = "COUNT"
    result = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert result.status_code == 201, result.text
    saved = result.json()
    assert saved["stock"]["lines"][0]["quantity"] == "0.0000"
    assert saved["stock"]["lines"][0]["count"] == stock_line["count"]
    detail = await client.get(prefix + "/vouchers/" + saved["id"], headers=auth())
    assert detail.json() == saved
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(VoucherStockDetail))).count == stock_line["count"]
