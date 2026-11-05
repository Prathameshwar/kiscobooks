"""Public count commands preserve scoped authority, replay and immutable observations."""

from decimal import Decimal
from zoneinfo import ZoneInfo

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import func, select

from accounting.api import stock as api
from accounting.models.stock_count import StockCountObservation
from tests.conftest import COMPANY, TENANT
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_stock_effects import source
from tests.test_stock_ledger import item, warehouse


async def test_count_api_is_scoped_reviewed_and_replay_survives_owner_outage(
    app, client, monkeypatch
):
    await journal_setup(client, app)
    product, location = item(), warehouse()
    location = location.model_copy(
        update={"allowed_operations": (*location.allowed_operations, "ADJUSTMENT")}
    )
    calls = []

    class Owner:
        async def acquire(self, request):
            calls.append(request)
            return source(request, product, location).model_copy(
                update={"purpose": request.purpose}
            )

        async def release(self, _facts):
            pass

    monkeypatch.setattr(api, "StockSourceClient", lambda *_: Owner())
    app.state.settings.stock_owner_url = "http://owner.invalid"
    app.state.settings.stock_owner_secret = SecretStr("qa-only-owner-source-secret")
    permissions = LEDGER_PERMISSIONS | {
        "accounting.stock.read",
        "accounting.stock.post",
        "accounting.stock.configure",
    }
    auth = ledger_headers(permissions=permissions, features={"inventory"})
    base = f"/v1/companies/{COMPANY}/stock/counts"
    body = {
        "item_id": str(product.item_id),
        "warehouse_id": str(location.warehouse_id),
        "stock_date": utcnow().astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
        "reason": "Controlled physical count",
    }
    result = await client.post(base, json=body, headers=auth | {"Idempotency-Key": "start-count"})
    assert result.status_code == 201, result.text
    count = result.json()
    assert count["status"] == "UNCOUNTED" and count["book_quantity"] == "0.0000"
    assert count["observed_quantity"] is None and count["base_unit_id"] == str(product.base_unit_id)
    app.state.settings.stock_owner_url = None
    app.state.settings.stock_owner_secret = None
    replay = await client.post(base, json=body, headers=auth | {"Idempotency-Key": "start-count"})
    assert replay.status_code == 201 and replay.json()["id"] == count["id"]
    assert replay.headers["Idempotency-Replayed"] == "true" and len(calls) == 1
    path = base + "/" + count["id"] + "/observations"
    observed = {"expected_revision": 1, "observed_quantity": "0", "reason": "Explicit counted zero"}
    zero = await client.post(
        path, json=observed, headers=auth | {"Idempotency-Key": "observed-zero"}
    )
    assert zero.status_code == 201, zero.text
    assert zero.json()["observed_quantity"] == "0.0000" and zero.json()["status"] == "OBSERVED"
    stale = await client.post(
        path, json=observed, headers=auth | {"Idempotency-Key": "stale-observation"}
    )
    assert stale.status_code == 409
    invalid = await client.post(
        path,
        json=observed | {"expected_revision": 2, "observed_quantity": "1.5"},
        headers=auth | {"Idempotency-Key": "fractional-count"},
    )
    assert invalid.status_code == 422
    denied_review = ledger_headers(
        permissions=permissions - {"accounting.stock.configure"}, features={"inventory"}
    )
    review = observed | {
        "expected_revision": 2,
        "observed_quantity": "1",
        "reviewed_unit_cost": "5",
        "cost_review_reason": "Verified reviewed cost",
    }
    refused = await client.post(
        path, json=review, headers=denied_review | {"Idempotency-Key": "unapproved-cost"}
    )
    assert refused.status_code == 403
    denied_read = ledger_headers(
        permissions=permissions,
        features={"inventory"},
        policies=[
            {
                "entity_type": "accounting.stock_movement",
                "field_key": "quantity",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ],
    )
    assert (await client.get(base + "/" + count["id"], headers=denied_read)).status_code == 403
    foreign = ledger_headers(tenant=uuid7(), permissions=permissions, features={"inventory"})
    assert (await client.get(base + "/" + count["id"], headers=foreign)).status_code == 404
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockCountObservation.id))) == 2
            latest = await db.scalar(
                select(StockCountObservation).order_by(StockCountObservation.revision.desc())
            )
            assert latest.observed_quantity == Decimal("0")
