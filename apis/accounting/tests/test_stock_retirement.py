"""Retirement checks physical/value custody and both ends of an open shipment."""

from decimal import Decimal

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7

from accounting.tasks.stock_retirement import no_stock
from accounting.tasks.stock_transfers import dispatch, receive
from tests.conftest import COMPANY, TENANT
from tests.test_stock_ledger import item, ledger, line, reconciles, warehouse


async def test_no_stock_is_location_specific_and_does_not_treat_zero_available_as_clear(app):
    product, location = item(), warehouse()
    first, second, empty = uuid7(), uuid7(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, bin_id=first),
                product,
                location,
                value=Decimal("10"),
            )
            await owner.receive(
                line(product, location, 1, bin_id=second),
                product,
                location,
                value=Decimal("20"),
            )
        async with app.state.session_factory.begin() as db:
            assert await no_stock(db, COMPANY, location.warehouse_id) == "STOCK_ON_HAND"
            assert (
                await no_stock(db, COMPANY, location.warehouse_id, bin_id=first) == "STOCK_ON_HAND"
            )
            assert await no_stock(db, COMPANY, location.warehouse_id, bin_id=empty) is None
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            await owner.issue(line(product, location, 1, bin_id=first), product, location)
            await owner.issue(line(product, location, 1, bin_id=second), product, location)
            await reconciles(db)
            assert await no_stock(db, COMPANY, location.warehouse_id) is None


async def test_open_transfer_blocks_source_and_destination_even_with_zero_local_quantity(app):
    product, source, target = item(), warehouse(), warehouse()
    transit = warehouse().model_copy(update={"kind": "INTERNAL_TRANSIT"})
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, source, 2), product, source, value=Decimal("30"))
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "TRANSFER_DISPATCH")
            _, shipment = await dispatch(
                owner,
                line(product, source, 2, destination_warehouse_id=target.warehouse_id),
                product,
                source,
                transit,
                target,
            )
        async with app.state.session_factory.begin() as db:
            assert await no_stock(db, COMPANY, source.warehouse_id) == "OPEN_TRANSFER"
            assert await no_stock(db, COMPANY, target.warehouse_id) == "OPEN_TRANSFER"
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "TRANSFER_RECEIPT")
            await receive(
                owner,
                line(product, target, 2, source_movement_id=shipment.movement_id),
                product,
                target,
                transit,
            )
            await reconciles(db)
        async with app.state.session_factory.begin() as db:
            assert await no_stock(db, COMPANY, source.warehouse_id) is None
            assert await no_stock(db, COMPANY, target.warehouse_id) == "STOCK_ON_HAND"
