"""Physical order follows eligible stock, independently from financial FIFO cost."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7

from accounting.models.stock_tracking import StockLot, StockUnit
from accounting.tasks.stock_selection import candidates
from tests.conftest import COMPANY, TENANT
from tests.test_stock_ledger import (
    DAY,
    item,
    ledger,
    line,
    preparation_source,
    prepare_serial,
    reconciles,
    values,
    warehouse,
)


async def test_selection_never_offers_receipts_after_requested_stock_date(app):
    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, day=DAY + dt.timedelta(days=1))
            await owner.receive(line(product, location, 2), product, location, value=Decimal("20"))
        async with app.state.session_factory.begin() as db:
            assert (
                await candidates(
                    db, company=COMPANY, item=product, warehouse=location.warehouse_id, day=DAY
                )
                == ()
            )


@pytest.mark.parametrize("strategy", ["FIFO", "FEFO"])
async def test_physical_batch_order_does_not_choose_financial_cost(app, strategy):
    product = item(tracking=True).model_copy(
        update={
            "serial_tracking": False,
            "issue_strategy": strategy,
        }
    )
    location, older, sooner = warehouse(), uuid7(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for identity, days in ((older, 20), (sooner, 2)):
                db.add(
                    StockLot(
                        **(values() | {"id": identity}),
                        item_id=product.item_id,
                        code=str(identity),
                        normalized_code=str(identity),
                        namespace_key="COMPANY",
                        source_party_id=None,
                        manufactured_on=DAY,
                        expires_on=DAY + dt.timedelta(days=days),
                        status="ACTIVE",
                        is_held=False,
                        source_facts=preparation_source(product),
                    )
                )
            await db.flush()
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, lot_id=older),
                product,
                location,
                value=Decimal("10"),
            )
            await owner.receive(
                line(product, location, 1, lot_id=sooner),
                product,
                location,
                value=Decimal("20"),
            )
        chosen, wrong = (older, sooner) if strategy == "FIFO" else (sooner, older)
        with pytest.raises(ConflictError, match="earliest eligible"):
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db, "DISPATCH")
                await owner.issue(line(product, location, 1, lot_id=wrong), product, location)
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(
                line(product, location, 1, lot_id=chosen),
                product,
                location,
            )
            assert issued.value == Decimal("-10")
            await reconciles(db)


async def test_serial_fifo_excludes_held_units_but_cannot_skip_older_available_units(app):
    product = item().model_copy(update={"serial_tracking": True, "issue_strategy": "FIFO"})
    location = warehouse()
    held, older, later = (uuid7() for _ in range(3))
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for identity in (held, older, later):
                await prepare_serial(db, product, identity)
                owner = await ledger(db)
                await owner.receive(
                    line(product, location, 1, unit_ids=(identity,)),
                    product,
                    location,
                    value=Decimal("10"),
                )
            unit = await db.get(StockUnit, held)
            unit.is_held = True
        with pytest.raises(ConflictError, match="earliest eligible"):
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db, "DISPATCH")
                await owner.issue(
                    line(product, location, 1, unit_ids=(later,)),
                    product,
                    location,
                )
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            await owner.issue(
                line(product, location, 1, unit_ids=(older,)),
                product,
                location,
            )
            await reconciles(db)
