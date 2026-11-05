"""Real MySQL writers serialize physical custody under Accounting's company lock."""

import asyncio
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from accounting.models.masters import AccountingSetup
from accounting.models.stock import StockBalance, StockMovement, StockPosting, StockUnitPosition
from accounting.tasks.stock_reconciliation import assert_physical
from tests.conftest import COMPANY, TENANT
from tests.test_stock_ledger import item, ledger, line, prepare_serial, warehouse


@pytest.mark.mysql
async def test_competing_writers_cannot_issue_the_same_last_serial_twice(app, engine):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("requires the disposable native MySQL fixture and real row locks")
    product = item().model_copy(update={"serial_tracking": True})
    location, unit = warehouse(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await prepare_serial(db, product, unit)
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, unit_ids=(unit,)),
                product,
                location,
                value=Decimal("12.50"),
            )
    first_locked, second_started = asyncio.Event(), asyncio.Event()

    async def issue(first):
        with tenant_scope(TENANT):
            try:
                async with app.state.session_factory.begin() as db:
                    if not first:
                        await first_locked.wait()
                        second_started.set()
                    await db.scalar(
                        select(AccountingSetup)
                        .where(AccountingSetup.company_id == COMPANY)
                        .with_for_update()
                    )
                    if first:
                        first_locked.set()
                        await second_started.wait()
                    owner = await ledger(db, "DISPATCH")
                    await owner.issue(
                        line(product, location, 1, unit_ids=(unit,)), product, location
                    )
                return True
            except ConflictError:
                return False

    async with asyncio.timeout(30):
        assert await asyncio.gather(issue(True), issue(False)) == [True, False]
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await assert_physical(db, COMPANY)
            assert (await db.scalar(select(StockBalance))).quantity == Decimal("0")
            assert (await db.scalar(select(StockUnitPosition))).position_id is None
            assert 1 == await db.scalar(
                select(func.count(StockPosting.id)).where(StockPosting.action == "DISPATCH")
            )
            assert 2 == await db.scalar(select(func.count(StockMovement.id)))
