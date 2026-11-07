"""Complete stock source is reconciled from the committed owner's native evidence."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from reporting_contract.inventory import Coverage, Position
from sqlalchemy import select

from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.models.stock import StockMovement, StockPosting
from accounting.tasks import stock_reporting
from accounting.tasks.stock_execution import dispatch
from accounting.tasks.stock_summary_source import publish_complete, recover_committed_movements
from tests.conftest import SECRET, TENANT
from tests.test_stock_reporting import request_for


@pytest.mark.parametrize("sale_eligible", [None, False])
async def test_complete_source_has_actual_quantity_cost_and_stable_identities(app, client, sale_eligible):
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
        {"kind": "LOCATION", "location_id": str(warehouse), "code": "MAIN", "name": "Main", "sale_eligible": sale_eligible},
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
            assert Decimal(position.eligible_quantity) == (Decimal("0") if sale_eligible is False else Decimal("2"))
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


async def test_missing_committed_movement_handoff_recovers_from_owner_receipt(app, client, monkeypatch):
    request, owner, facts = await request_for(app, client)
    original_capture = stock_reporting.capture

    async def skip_capture(*args, **kwargs):
        return None

    monkeypatch.setattr(stock_reporting, "capture", skip_capture)
    receipt = await dispatch(
        app.state.session_factory, request, secret=SECRET.encode(),
        client=owner, source_client=facts, enabled=True,
    )
    assert receipt.outcome == "COMMITTED"
    monkeypatch.setattr(stock_reporting, "capture", original_capture)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            postings = {row.id: row for row in await db.scalars(select(StockPosting))}
            movements = list(await db.scalars(select(StockMovement)))
            await recover_committed_movements(
                db, company=request.company_id, postings=postings,
                movements=movements, reported=set(),
            )
        async with app.state.session_factory() as db:
            records = list(await db.scalars(select(InventoryReportRecord)))
            assert len(records) == 1
            assert records[0].payload["voucher_number"] == "GRN/26/001"
