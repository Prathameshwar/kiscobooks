"""Review diagnostics: reproduce defects on disposable native storage only."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from sqlalchemy import delete, func, select

from accounting.models.stock import StockBalance, StockPosting
from accounting.tasks.stock_reconciliation import assert_physical
from accounting.tasks.stock_reporting import capture
from tests.conftest import COMPANY, TENANT
from tests.test_stock_ledger import item, ledger, line, warehouse
from tests.test_stock_reads import BASE, auth, seed


async def test_numbered_unchanged_count_is_rejected_by_empty_reporting_handoff(app):
    # A native zero-difference count creates a posting/claim and no movements.
    # Isolate that actual handoff boundary from unrelated HTTP setup failures.
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            product, location = item(), warehouse()
            receipt = await ledger(db)
            await receipt.receive(
                line(product, location, 2), product, location, value=Decimal("12.50")
            )
        with pytest.raises(ConflictError, match="native execution bound"):
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db, action="COUNT")
                command = SimpleNamespace(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    execution_id=owner.posting.execution_id,
                    voucher_id=owner.posting.voucher_id,
                    voucher_number="COUNT/REVIEW/001",
                )
                result = SimpleNamespace(
                    outcome="COMMITTED",
                    committed_generation=2,
                    effects=[
                        SimpleNamespace(effect_kind="STOCK", effect_id=owner.posting.id)
                    ],
                )
                await capture(db, command, result)
        async with app.state.session_factory() as db:
            assert await db.scalar(select(StockBalance.quantity)) == Decimal("2")
            assert (
                await db.scalar(
                    select(func.count(StockPosting.id)).where(
                        StockPosting.action == "COUNT"
                    )
                )
                == 0
            )


async def test_missing_balance_is_silently_hidden_from_position_list(app, client):
    product, _, _ = await seed(app)
    # Deliberately corrupt only the disposable fixture through Core. The ORM's
    # deletion guard is correct and remains enabled; this models recovery damage.
    async with app.state.engine.begin() as connection:
        await connection.execute(
            delete(StockBalance.__table__).where(StockBalance.company_id == COMPANY)
        )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            with pytest.raises(ConflictError, match="reconcile"):
                await assert_physical(db, COMPANY)
    response = await client.get(
        BASE + "/positions", params={"item_id": str(product.item_id)}, headers=auth()
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
    history = await client.get(BASE + "/movements", headers=auth())
    assert history.status_code == 200 and len(history.json()["items"]) == 1
    pools = await client.get(BASE + "/cost-pools", headers=auth())
    assert pools.status_code == 200 and pools.json()["items"][0]["quantity"] == "2.0000"


async def test_missing_balance_detail_raises_raw_no_result(app, client):
    import httpx

    _, _, movement = await seed(app)
    async with app.state.engine.begin() as connection:
        await connection.execute(
            delete(StockBalance.__table__).where(StockBalance.company_id == COMPANY)
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://accounting.test",
    ) as browser:
        response = await browser.get(
            BASE + "/positions/" + str(movement.position_id), headers=auth()
        )
    assert response.status_code == 500


async def test_native_serial_handoff_discards_retained_unit_identities(app):
    from types import SimpleNamespace
    from billing_platform.ids import uuid7
    from accounting.models.inventory_reporting import InventoryReportRecord
    from accounting.models.stock import StockMovementUnit
    from accounting.models.stock_tracking import StockLot
    from accounting.tasks.stock_reporting import capture
    from tests.test_stock_ledger import (
        DAY,
        ledger,
        line,
        preparation_source,
        prepare_serial,
        values,
    )

    product, location = item(tracking=True), warehouse()
    lot_id, unit_id = uuid7(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            db.add(
                StockLot(
                    **(values() | {"id": lot_id}),
                    item_id=product.item_id,
                    code="REVIEW-LOT",
                    normalized_code="review-lot",
                    namespace_key="COMPANY",
                    manufactured_on=DAY,
                    expires_on=DAY,
                    status="ACTIVE",
                    is_held=False,
                    source_facts=preparation_source(product),
                )
            )
            await db.flush()
            await prepare_serial(db, product, unit_id, lot_id)
            owner = await ledger(db)
            movement = await owner.receive(
                line(product, location, 1, lot_id=lot_id, unit_ids=(unit_id,)),
                product,
                location,
                value=Decimal("10"),
            )
            command = SimpleNamespace(
                tenant_id=TENANT,
                company_id=COMPANY,
                execution_id=owner.posting.execution_id,
                voucher_id=owner.posting.voucher_id,
                voucher_number="SERIAL/REVIEW/001",
            )
            result = SimpleNamespace(
                outcome="COMMITTED",
                committed_generation=1,
                effects=[
                    SimpleNamespace(effect_kind="STOCK", effect_id=owner.posting.id)
                ],
            )
            await capture(db, command, result)
            await db.flush()
            record = await db.get(InventoryReportRecord, movement.movement_id)
            assert record.payload["serials"] == []
            assert await db.scalar(select(func.count(StockMovementUnit.id))) == 1
