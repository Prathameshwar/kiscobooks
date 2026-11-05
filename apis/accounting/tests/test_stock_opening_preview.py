"""Public calculation is exact, field protected and incapable of writing stock."""

from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import func, select
from voucher_execution.opening import OpeningUnitFact

from accounting.models.stock import StockPosting
from accounting.tasks.stock_source_client import StockSourceClient
from tests.conftest import COMPANY, TENANT
from tests.test_stock_effects import source
from tests.test_stock_ledger import item, warehouse
from tests.test_stock_opening_api import BASE, auth


@pytest.mark.parametrize("measured", [False, True])
async def test_calculation_pins_conversion_and_rejects_protected_inputs(
    client, app, monkeypatch, measured
):
    product, location, revision = item(), warehouse(), uuid7()
    unit = OpeningUnitFact(
        item_id=product.item_id,
        unit_id=uuid7(),
        revision_id=revision,
        numerator=None if measured else 12,
        denominator=None if measured else 1,
        conversion_mode="MEASURED" if measured else "FIXED",
        quantity_increment=Decimal("1"),
        quantity_decimal_places=0,
    )
    product = product.model_copy(update={"opening_units": (unit,)})
    app.state.settings = app.state.settings.model_copy(
        update={
            "stock_owner_url": "http://127.0.0.1:8003",
            "stock_owner_secret": SecretStr("ephemeral-test-source-key" * 2),
        }
    )
    calls = []

    async def acquire(self, request):
        calls.append(request)
        return source(request, product, location).model_copy(update={"purpose": "PREVIEW"})

    monkeypatch.setattr(StockSourceClient, "acquire", acquire)
    body = {
        "stock_date": "2026-04-01",
        "item_id": str(product.item_id),
        "warehouse_id": str(location.warehouse_id),
        "opening": {
            "source_key": "preview-a",
            "entered_unit_id": str(unit.unit_id),
            "unit_revision_id": str(revision),
            "entered_quantity": "2",
            **({"measured_base_quantity": "24"} if measured else {}),
            "unit_cost": "120.005",
            "priced_quantity": "1",
            "cost_mode": "RATE",
            "history_known": False,
        },
    }
    result = await client.post(BASE + "/calculate", json=body, headers=auth())
    assert result.status_code == 200, result.text
    assert result.json()["base_quantity"] == "24.0000"
    assert result.json()["received_value"] == "240.0100"
    assert result.json()["informational_only"]
    assert calls[0].opening_unit_revision_ids == (revision,)
    assert (
        await client.post(
            BASE + "/calculate", json=body | {"received_value": "240"}, headers=auth()
        )
    ).status_code == 422
    for entity, field in (
        ("stock_movement", "opening"),
        ("stock_movement", "received_value"),
        ("stock_posting", "currency"),
        ("stock_position", "quantity"),
    ):
        signed = auth(
            policies=[
                {
                    "entity_type": "accounting." + entity,
                    "field_key": field,
                    "effect": "deny",
                    "access": "read",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        )
        before = len(calls)
        assert (
            await client.post(BASE + "/calculate", json=body, headers=signed)
        ).status_code == 403
        assert len(calls) == before
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 0


async def test_opening_body_limit_precedes_parsing_and_requires_bounded_content(client):
    result = await client.post(
        BASE, content=b" " * 2_097_153, headers={"Content-Type": "application/json"}
    )
    assert result.status_code == 413 and result.json()["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize("reason", ["   ", "bad\nreason"])
async def test_opening_reason_requires_printable_evidence(client, reason):
    result = await client.post(
        BASE + "/confirm-zero", json={"expected_generation": 1, "reason": reason}, headers=auth()
    )
    assert result.status_code == 422
