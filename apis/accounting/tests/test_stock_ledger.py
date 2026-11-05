"""Real storage conservation for physical stock, costs, cohorts and serial custody."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode
from sqlalchemy import func, select
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact, StockWarehouseFact

from accounting.domain.master_metadata import METADATA_VERSION
from accounting.models.masters import AccountingSetup
from accounting.models.stock import (
    StockBalance,
    StockCostLayer,
    StockCostPool,
    StockMovement,
    StockMovementUnit,
    StockOriginAllocation,
    StockOriginBalance,
    StockPosition,
    StockPosting,
    StockReceiptOrigin,
    StockUnitPosition,
    StockValueEntry,
)
from accounting.models.stock_tracking import StockLot, StockUnit, StockUnitIdentifier
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.stock_tracking import TrackingSource
from accounting.tasks.stock_ledger import StockLedger
from tests.conftest import COMPANY, TENANT, USER

DAY = dt.date(2026, 10, 28)


def values():
    return {
        "id": uuid7(),
        "tenant_id": TENANT,
        "company_id": COMPANY,
        "created_by": USER,
        "updated_by": USER,
        "row_version": 1,
    }


def item(method="FIFO", *, tracking=False):
    return StockItemFact(
        item_id=uuid7(),
        family_id=uuid7(),
        item_version=1,
        family_version=1,
        status="ACTIVE",
        family_status="ACTIVE",
        base_unit_id=uuid7(),
        quantity_increment="1",
        quantity_decimal_places=0,
        profile_id=uuid7(),
        profile_revision_id=uuid7(),
        lot_tracking=tracking,
        serial_tracking=tracking,
        expiry_required=tracking,
        manufacture_date_required=tracking,
        shelf_life_days=None,
        minimum_remaining_life_days=0,
        issue_strategy="FEFO",
        valuation_method=method,
        negative_stock_policy="BLOCK",
        sellable=True,
        purchasable=True,
        allowed_warehouse_ids=None,
        warehouse_permissions=(),
    )


def warehouse():
    return StockWarehouseFact(
        warehouse_id=uuid7(),
        row_version=1,
        kind="GODOWN",
        is_active=True,
        department_id=None,
        policy_revision_id=uuid7(),
        allowed_operations=(
            "PURCHASE_RECEIPT",
            "SALE_ISSUE",
            "TRANSFER_IN",
            "TRANSFER_OUT",
            "OPENING_STOCK",
        ),
    )


def line(product, location, quantity, **changes):
    return StockLine(
        line_id=uuid7(),
        item_id=product.item_id,
        warehouse_id=location.warehouse_id,
        quantity=str(quantity),
        **changes,
    )


def preparation_source(product):
    return TrackingSource(
        company_id=COMPANY,
        item_id=product.item_id,
        as_of=DAY,
        profile_revision_id=product.profile_revision_id,
        lot_tracking=product.lot_tracking,
        serial_tracking=product.serial_tracking,
        expiry_required=product.expiry_required,
        manufacture_date_required=product.manufacture_date_required,
        shelf_life_days=product.shelf_life_days,
        minimum_remaining_life_days=product.minimum_remaining_life_days,
        source_digest="a" * 64,
        requirements=[
            {
                "identifier_type": "SERIAL",
                "namespace_rule": "COMPANY",
                "min_count": 1,
                "max_count": 1,
                "requires_slot": False,
            }
        ]
        if product.serial_tracking
        else [],
    ).model_dump(mode="json")


async def prepare_serial(db, product, identity, lot_id=None):
    db.add(
        StockUnit(
            **(values() | {"id": identity}),
            item_id=product.item_id,
            lot_id=lot_id,
            status="ACTIVE",
            is_held=False,
            source_facts=preparation_source(product),
        )
    )
    await db.flush()
    db.add(
        StockUnitIdentifier(
            **values(),
            unit_id=identity,
            identifier_type="SERIAL",
            slot=1,
            value=str(identity),
            normalized_value=str(identity),
            namespace_key="COMPANY",
            normalization_version=1,
        )
    )
    await db.flush()


async def ledger(
    db, action="RECEIPT", day=DAY, *, reverses_id=None, stock=None, account_policy_id=None
):
    if (
        await db.scalar(select(AccountingSetup.id).where(AccountingSetup.company_id == COMPANY))
        is None
    ):
        db.add(
            AccountingSetup(
                **values(), base_currency="INR", generation=1, metadata_version=METADATA_VERSION
            )
        )
        await db.flush()
    execution = uuid7()
    intent = VoucherMoneyIntent(
        **values(),
        execution_id=execution,
        voucher_id=uuid7(),
        journal_id=None,
        request_hash="a" * 64,
        kind="STOCK_JOURNAL",
        posting_date=day,
        status="PREPARED",
        command={},
    )
    db.add(intent)
    await db.flush()
    posting = StockPosting(
        **values(),
        intent_id=intent.id,
        execution_id=execution,
        operation_id=uuid7(),
        voucher_id=intent.voucher_id,
        revision_id=uuid7(),
        action=action,
        stock_date=day,
        posting_date=day,
        currency="INR",
        journal_id=None,
        reverses_id=reverses_id,
        account_policy_id=account_policy_id,
        content_hash="a" * 64,
        source_facts={"stock": stock} if stock else {},
    )
    db.add(posting)
    await db.flush()
    return StockLedger(
        db,
        posting,
        actor_id=USER,
        timezone="Asia/Kolkata",
        places=2,
        rounding=RoundingMode.HALF_UP,
        now=dt.datetime(2026, 10, 29, tzinfo=dt.UTC),
    )


async def reconciles(db):
    for position in await db.scalars(select(StockPosition)):
        balance = await db.scalar(
            select(StockBalance).where(StockBalance.position_id == position.id)
        )
        movement_quantity = await db.scalar(
            select(func.sum(StockMovement.quantity)).where(StockMovement.position_id == position.id)
        )
        physical_quantity = await db.scalar(
            select(func.sum(StockOriginBalance.quantity)).where(
                StockOriginBalance.position_id == position.id
            )
        )
        assert balance.quantity == (movement_quantity or 0) == (physical_quantity or 0)
    for pool in await db.scalars(select(StockCostPool)):
        assert pool.quantity == await db.scalar(
            select(func.sum(StockMovement.quantity)).where(StockMovement.pool_id == pool.id)
        )
        assert pool.value == await db.scalar(
            select(func.sum(StockValueEntry.amount)).where(StockValueEntry.pool_id == pool.id)
        )
        if pool.method == "FIFO":
            assert pool.quantity == await db.scalar(
                select(func.sum(StockCostLayer.remaining_quantity)).where(
                    StockCostLayer.pool_id == pool.id
                )
            )
            assert pool.value == await db.scalar(
                select(func.sum(StockCostLayer.remaining_value)).where(
                    StockCostLayer.pool_id == pool.id
                )
            )
    for origin in await db.scalars(select(StockReceiptOrigin)):
        residual = await db.scalar(
            select(func.sum(StockOriginBalance.quantity)).where(
                StockOriginBalance.origin_id == origin.id
            )
        )
        allocations = await db.scalar(
            select(func.sum(StockOriginAllocation.quantity)).where(
                StockOriginAllocation.origin_id == origin.id
            )
        )
        assert residual == allocations
    from accounting.tasks.stock_reconciliation import assert_physical

    await assert_physical(db, COMPANY)


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_warehouse_costs_transfer_conservation_and_negative_rollback(app, method):
    factory = app.state.session_factory
    product, first, second = item(method), warehouse(), warehouse()
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            owner = await ledger(db)
            receipt = await owner.receive(
                line(product, first, 4), product, first, value=Decimal("40")
            )
            owner = await ledger(db)
            await owner.receive(line(product, first, 2), product, first, value=Decimal("50"))
        async with factory.begin() as db:
            owner = await ledger(db, "TRANSFER")
            out, inward = await owner.transfer(
                line(product, first, 2, destination_warehouse_id=second.warehouse_id),
                product,
                first,
                second,
            )
            assert out.value == (-20 if method == "FIFO" else -30)
            assert out.value + inward.value == 0
            assert inward.origins[0].origin_id == receipt.origins[0].origin_id
            await reconciles(db)
        async with factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issue = await owner.issue(line(product, second, 1), product, second)
            assert issue.value == (-10 if method == "FIFO" else -15)
            await reconciles(db)
        with pytest.raises(ConflictError, match="insufficient"):
            async with factory.begin() as db:
                owner = await ledger(db, "DISPATCH")
                await owner.issue(line(product, second, 2), product, second)
        async with factory() as db:
            await reconciles(db)
            assert await db.scalar(select(func.count(StockPosting.id))) == 4


async def test_bin_transfer_preserves_fifo_sequence_and_original_physical_age(app):
    factory = app.state.session_factory
    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            owner = await ledger(db)
            first = await owner.receive(
                line(product, location, 2), product, location, value=Decimal("20")
            )
            owner = await ledger(db)
            await owner.receive(line(product, location, 2), product, location, value=Decimal("40"))
        async with factory.begin() as db:
            owner = await ledger(db, "TRANSFER")
            out, inward = await owner.transfer(
                line(
                    product,
                    location,
                    1,
                    destination_warehouse_id=location.warehouse_id,
                    destination_bin_id=uuid7(),
                ),
                product,
                location,
                location,
            )
            assert inward.origins[0].origin_id == first.origins[0].origin_id
            assert await db.scalar(select(func.count(StockCostLayer.id))) == 2
            await reconciles(db)
        async with factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(line(product, location, 1), product, location)
            assert issued.value == Decimal("-10")
            await reconciles(db)


async def test_serial_preparation_receipt_custody_scoped_transfer_and_exact_cost(app):
    factory = app.state.session_factory
    product, first, second = item(tracking=True), warehouse(), warehouse()
    lot_id = uuid7()
    units = [uuid7() for _ in range(3)]
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            lot = StockLot(
                **(values() | {"id": lot_id}),
                item_id=product.item_id,
                code="SERIAL-BATCH",
                normalized_code="serial-batch",
                namespace_key="COMPANY",
                source_party_id=None,
                manufactured_on=DAY,
                expires_on=DAY,
                status="ACTIVE",
                is_held=False,
                source_facts=preparation_source(product),
            )
            db.add(lot)
            await db.flush()
            for identity in units:
                await prepare_serial(db, product, identity, lot_id=lot_id)
            await db.flush()
            assert await db.scalar(select(func.count(StockUnitPosition.id))) == 0
            assert await db.scalar(select(func.count(StockBalance.id))) == 0
        async with factory.begin() as db:
            owner = await ledger(db)
            received = await owner.receive(
                line(product, first, 3, lot_id=lot_id, unit_ids=tuple(units)),
                product,
                first,
                value=Decimal("1"),
            )
            assert sum((unit.carrying_value for unit in received.units), Decimal(0)) == 1
            assert [unit.carrying_value for unit in received.units] == [
                Decimal(".33"),
                Decimal(".34"),
                Decimal(".33"),
            ]
        with pytest.raises(ConflictError, match="history"):
            async with factory.begin() as db:
                owner = await ledger(db)
                await owner.receive(
                    line(product, first, 1, lot_id=lot_id, unit_ids=(units[0],)),
                    product,
                    first,
                    value=Decimal("3"),
                )
        async with factory.begin() as db:
            owner = await ledger(db, "TRANSFER")
            out, inward = await owner.transfer(
                line(
                    product,
                    first,
                    1,
                    lot_id=lot_id,
                    unit_ids=(units[0],),
                    destination_warehouse_id=second.warehouse_id,
                ),
                product,
                first,
                second,
            )
            assert out.units == inward.units
            state = await db.scalar(
                select(StockUnitPosition).where(StockUnitPosition.unit_id == units[0])
            )
            assert state.position_id == inward.position_id
            assert state.origin_id == received.origins[0].origin_id
            assert await db.scalar(select(func.count(StockMovementUnit.id))) == 5
            await reconciles(db)
        with pytest.raises(ConflictError, match="not available"):
            async with factory.begin() as db:
                owner = await ledger(db, "DISPATCH")
                await owner.issue(
                    line(product, first, 1, lot_id=lot_id, unit_ids=(units[0],)), product, first
                )
        with pytest.raises(ConflictError, match="expired"):
            async with factory.begin() as db:
                owner = await ledger(db, "DISPATCH", DAY + dt.timedelta(days=1))
                await owner.issue(
                    line(product, second, 1, lot_id=lot_id, unit_ids=(units[0],)), product, second
                )
        async with factory() as db:
            await reconciles(db)


async def test_backdating_affecting_later_warehouse_cost_is_rejected_atomically(app):
    product, location = item(), warehouse()
    factory = app.state.session_factory
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 1), product, location, value=Decimal("10"))
        with pytest.raises(ConflictError, match="backdated"):
            async with factory.begin() as db:
                owner = await ledger(db, "RECEIPT", DAY - dt.timedelta(days=1))
                await owner.receive(
                    line(product, location, 1), product, location, value=Decimal("30")
                )
        async with factory() as db:
            await reconciles(db)
            assert await db.scalar(select(func.count(StockPosting.id))) == 1


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_linked_returns_reuse_original_cost_and_cannot_claim_twice(app, method):
    from accounting.tasks.stock_claims import customer_return, supplier_return

    factory = app.state.session_factory
    product, location = item(method), warehouse()
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            owner = await ledger(db)
            receipt = await owner.receive(
                line(product, location, 3), product, location, value=Decimal("30")
            )
            owner = await ledger(db)
            await owner.receive(line(product, location, 3), product, location, value=Decimal("60"))
        async with factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            dispatched = await owner.issue(line(product, location, 2), product, location)
        async with factory.begin() as db:
            owner = await ledger(db, "CUSTOMER_RETURN")
            returned, source = await customer_return(
                owner,
                line(product, location, 1, source_movement_id=dispatched.movement_id),
                product,
                location,
            )
            assert returned.value == -dispatched.value / 2 == source.value
            assert returned.origins[0].origin_id == receipt.origins[0].origin_id
            await reconciles(db)
        async with factory.begin() as db:
            owner = await ledger(db, "CUSTOMER_RETURN")
            returned, _ = await customer_return(
                owner,
                line(product, location, 1, source_movement_id=dispatched.movement_id),
                product,
                location,
            )
            assert returned.value == -dispatched.value / 2
            await reconciles(db)
        with pytest.raises(ConflictError, match="exceeds"):
            async with factory.begin() as db:
                owner = await ledger(db, "CUSTOMER_RETURN")
                await customer_return(
                    owner,
                    line(product, location, 1, source_movement_id=dispatched.movement_id),
                    product,
                    location,
                )
        async with factory.begin() as db:
            owner = await ledger(db, "SUPPLIER_RETURN")
            returned, source = await supplier_return(
                owner,
                line(product, location, 1, source_movement_id=receipt.movement_id),
                product,
                location,
            )
            assert source.value == Decimal("10")  # GRNI releases original cost.
            if method == "MOVING_AVERAGE":
                assert returned.value == Decimal(
                    "-15"
                )  # Current carrying cost; variance is explicit.
            await reconciles(db)


async def test_customer_serial_return_restores_that_units_cost_and_rejects_replay(app):
    from accounting.tasks.stock_claims import customer_return

    factory = app.state.session_factory
    product, location = item(), warehouse()
    product = product.model_copy(update={"serial_tracking": True})
    identities = [uuid7() for _ in range(3)]
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            for identity in identities:
                await prepare_serial(db, product, identity, lot_id=None)
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 3, unit_ids=tuple(identities)),
                product,
                location,
                value=Decimal("1"),
            )
        async with factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(
                line(product, location, 3, unit_ids=tuple(identities)), product, location
            )
        async with factory.begin() as db:
            owner = await ledger(db, "CUSTOMER_RETURN")
            returned, source = await customer_return(
                owner,
                line(
                    product,
                    location,
                    1,
                    unit_ids=(identities[1],),
                    source_movement_id=issued.movement_id,
                ),
                product,
                location,
            )
            assert source.value == returned.value == Decimal(".34")
            assert returned.units[0].unit_id == identities[1]
            await reconciles(db)
        with pytest.raises(ConflictError, match="no longer awaiting"):
            async with factory.begin() as db:
                owner = await ledger(db, "CUSTOMER_RETURN")
                await customer_return(
                    owner,
                    line(
                        product,
                        location,
                        1,
                        unit_ids=(identities[1],),
                        source_movement_id=issued.movement_id,
                    ),
                    product,
                    location,
                )
        async with factory() as db:
            await reconciles(db)


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_partial_transit_receipts_claim_only_their_shipment_and_destination(app, method):
    from voucher_execution.stock import StockInput

    from accounting.tasks.stock_transfers import dispatch, receive

    factory = app.state.session_factory
    product, first, second = item(method), warehouse(), warehouse()
    transit = warehouse().model_copy(update={"kind": "INTERNAL_TRANSIT"})
    transfer_line = line(product, first, 3, destination_warehouse_id=second.warehouse_id)
    source = StockInput(
        action="TRANSFER_DISPATCH",
        stock_date=DAY,
        currency="INR",
        lines=(transfer_line,),
        reason="Ship goods to a second warehouse",
    )
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, first, 6), product, first, value=Decimal("2"))
        async with factory.begin() as db:
            owner = await ledger(db, "TRANSFER_DISPATCH", stock=source.model_dump(mode="json"))
            _, pending = await dispatch(owner, transfer_line, product, first, transit, second)
            await reconciles(db)
        with pytest.raises(ConflictError, match="destination"):
            async with factory.begin() as db:
                owner = await ledger(db, "TRANSFER_RECEIPT")
                await receive(
                    owner,
                    line(product, first, 1, source_movement_id=pending.movement_id),
                    product,
                    first,
                    transit,
                )
        for count in (1, 2):
            async with factory.begin() as db:
                owner = await ledger(db, "TRANSFER_RECEIPT")
                outward, inward, claimed = await receive(
                    owner,
                    line(product, second, count, source_movement_id=pending.movement_id),
                    product,
                    second,
                    transit,
                )
                assert outward.value + inward.value == 0
                assert inward.value == claimed.value
                await reconciles(db)
        with pytest.raises(ConflictError, match="exceeds"):
            async with factory.begin() as db:
                owner = await ledger(db, "TRANSFER_RECEIPT")
                await receive(
                    owner,
                    line(product, second, 1, source_movement_id=pending.movement_id),
                    product,
                    second,
                    transit,
                )
        async with factory() as db:
            await reconciles(db)


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_reversal_restores_original_layers_after_dependent_issue_is_reversed(app, method):
    from accounting.tasks.stock_reversal import guard, reverse_leg

    factory = app.state.session_factory
    product, location = item(method), warehouse()
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            owner = await ledger(db)
            original_id = owner.posting.id
            await owner.receive(line(product, location, 3), product, location, value=Decimal("10"))
        async with factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issue_id = owner.posting.id
            await owner.issue(line(product, location, 1), product, location)
        with pytest.raises(ConflictError, match="dependent"):
            async with factory.begin() as db:
                owner = await ledger(db, "REVERSAL", reverses_id=original_id)
                await guard(owner, await db.get(StockPosting, original_id))
        async with factory.begin() as db:
            owner = await ledger(db, "REVERSAL", reverses_id=issue_id)
            for movement in await guard(owner, await db.get(StockPosting, issue_id)):
                await reverse_leg(owner, movement, product, location)
            await reconciles(db)
        async with factory.begin() as db:
            owner = await ledger(db, "REVERSAL", reverses_id=original_id)
            for movement in await guard(owner, await db.get(StockPosting, original_id)):
                await reverse_leg(owner, movement, product, location)
            await reconciles(db)
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == pool.value == 0
        async with factory() as db:
            await reconciles(db)
            assert await db.scalar(select(func.count(StockMovement.id))) == 4


async def test_reversing_serial_return_reopens_its_exact_source_claim(app):
    from accounting.tasks.stock_claims import customer_return
    from accounting.tasks.stock_reversal import guard, reverse_leg

    factory = app.state.session_factory
    product, location = item(), warehouse()
    product = product.model_copy(update={"serial_tracking": True})
    identity = uuid7()
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            await prepare_serial(db, product, identity, lot_id=None)
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, unit_ids=(identity,)),
                product,
                location,
                value=Decimal("10"),
            )
        async with factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            original = await owner.issue(
                line(product, location, 1, unit_ids=(identity,)), product, location
            )
        async with factory.begin() as db:
            owner = await ledger(db, "CUSTOMER_RETURN")
            return_id = owner.posting.id
            await customer_return(
                owner,
                line(
                    product,
                    location,
                    1,
                    unit_ids=(identity,),
                    source_movement_id=original.movement_id,
                ),
                product,
                location,
            )
        async with factory.begin() as db:
            owner = await ledger(db, "REVERSAL", reverses_id=return_id)
            for movement in await guard(owner, await db.get(StockPosting, return_id)):
                await reverse_leg(owner, movement, product, location)
            await reconciles(db)
        async with factory.begin() as db:
            owner = await ledger(db, "CUSTOMER_RETURN")
            returned, source = await customer_return(
                owner,
                line(
                    product,
                    location,
                    1,
                    unit_ids=(identity,),
                    source_movement_id=original.movement_id,
                ),
                product,
                location,
            )
            assert returned.value == source.value == Decimal("10")
            await reconciles(db)


async def test_unverified_prepared_serial_cannot_receive_stock(app):
    product, location, identity = item(), warehouse(), uuid7()
    product = product.model_copy(update={"serial_tracking": True})
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            db.add(
                StockUnit(
                    **(values() | {"id": identity}),
                    item_id=product.item_id,
                    lot_id=None,
                    status="ACTIVE",
                    is_held=False,
                    source_facts={},
                )
            )
            await db.flush()
        with pytest.raises(ConflictError, match="tracking"):
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db)
                await owner.receive(
                    line(product, location, 1, unit_ids=(identity,)),
                    product,
                    location,
                    value=Decimal("10"),
                )


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_reversed_initial_serial_receipt_can_be_corrected_without_new_identity(app, method):
    from accounting.tasks.stock_reversal import guard, reverse_leg

    product = item(method).model_copy(update={"serial_tracking": True})
    location, identity = warehouse(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await prepare_serial(db, product, identity)
            owner = await ledger(db)
            original = owner.posting.id
            await owner.receive(
                line(product, location, 1, unit_ids=(identity,)),
                product,
                location,
                value=Decimal("10"),
            )
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "REVERSAL", reverses_id=original)
            for movement in await guard(owner, await db.get(StockPosting, original)):
                await reverse_leg(owner, movement, product, location)
            await reconciles(db)
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, unit_ids=(identity,)),
                product,
                location,
                value=Decimal("12"),
            )
            await reconciles(db)
            assert await db.scalar(select(func.count(StockUnit.id))) == 1
            assert await db.scalar(select(StockBalance.quantity)) == 1
            assert await db.scalar(select(StockCostPool.value)) == Decimal("12")


async def test_physical_receipt_age_ties_survive_transfer_without_changing_cost_fifo(app):
    product, first, second = item(), warehouse(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            original = await owner.receive(
                line(product, first, 1), product, first, value=Decimal("10")
            )
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, second, 1), product, second, value=Decimal("20"))
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "TRANSFER")
            await owner.transfer(
                line(product, first, 1, destination_warehouse_id=second.warehouse_id),
                product,
                first,
                second,
            )
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(line(product, second, 1), product, second)
            assert issued.value == Decimal(
                "-20"
            )  # Financial FIFO follows arrival at this warehouse.
            assert (
                issued.origins[0].origin_id == original.origins[0].origin_id
            )  # Receipt age preserves company origin.
            await reconciles(db)
