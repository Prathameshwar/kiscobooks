"""Complete stock source is reconciled from the committed owner's native evidence."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from reporting_contract.inventory import Coverage, Position
from sqlalchemy import select

from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.tasks.stock_execution import dispatch
from accounting.tasks.stock_summary_source import publish_complete
from tests.conftest import SECRET, TENANT
from tests.test_stock_reporting import request_for


async def test_complete_source_has_actual_quantity_cost_and_stable_identities(app, client):
    request, owner, facts = await request_for(app, client)
    receipt = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=facts,
        enabled=True,
    )
    assert receipt.outcome == "COMMITTED"
    import uuid

    product = uuid.UUID(request.source_payload["stock"]["lines"][0]["item_id"])
    warehouse = uuid.UUID(request.source_payload["stock"]["lines"][0]["warehouse_id"])
    masters = [
        {
            "kind": "ITEM",
            "item_id": str(product),
            "code": "STOCK-1",
            "name": "Stock item",
            "unit": "PCS",
            "active": True,
            "lot_tracked": False,
            "serial_tracked": False,
        },
        {"kind": "LOCATION", "location_id": str(warehouse), "code": "MAIN", "name": "Main"},
    ]
    with tenant_scope(TENANT):
        for _ in range(2):
            async with app.state.session_factory.begin() as db:
                await publish_complete(
                    db,
                    tenant=TENANT,
                    company=request.company_id,
                    as_of=request.stock_date,
                    masters=masters,
                    policy_hash="a" * 64,
                )
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(InventoryReportRecord)))
            coverage = Coverage.model_validate(
                next(r.payload for r in rows if r.payload["kind"] == "COVERAGE")
            )
            position = Position.model_validate(
                next(r.payload for r in rows if r.payload["kind"] == "POSITION")
            )
            assert coverage.complete_company and coverage.movements_complete
            assert coverage.item_count == coverage.position_count == coverage.movement_count == 1
            assert Decimal(position.quantity) == Decimal("2")
            assert Decimal(position.carrying_value) == Decimal("12.50")
            assert Decimal(position.inward_quantity) == Decimal("2")
            assert position.valuation_detail is not None
            assert coverage.origins_complete
            assert sum(Decimal(origin.quantity) for origin in position.origins) == Decimal(
                position.quantity
            )
            assert len(rows) == 5
        with pytest.raises(ConflictError, match="master"):
            async with app.state.session_factory.begin() as db:
                await publish_complete(
                    db,
                    tenant=TENANT,
                    company=request.company_id,
                    as_of=request.stock_date,
                    masters=masters[1:],
                    policy_hash="a" * 64,
                )
        from accounting.models.stock import StockCostPool

        async with app.state.session_factory.begin() as db:
            pool = await db.scalar(select(StockCostPool))
            pool.value += Decimal("1")
        async with app.state.session_factory() as db:
            coverage_row = await db.scalar(
                select(InventoryReportRecord).where(
                    InventoryReportRecord.payload["kind"].as_string() == "COVERAGE"
                )
            )
            assert coverage_row.payload["native_stock_current"] is False


async def test_uninitialized_company_cannot_claim_empty_stock(app):
    import uuid

    with tenant_scope(TENANT):
        with pytest.raises(ConflictError):
            async with app.state.session_factory.begin() as db:
                await publish_complete(
                    db,
                    tenant=TENANT,
                    company=uuid.uuid4(),
                    as_of=dt.date.today(),
                    masters=[],
                    policy_hash="a" * 64,
                )
