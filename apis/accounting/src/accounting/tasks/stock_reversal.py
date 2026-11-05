"""Compensating physical evidence; original movements and costs stay immutable."""

from __future__ import annotations

from billing_platform.errors import ConflictError
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact, StockWarehouseFact

from accounting.domain.stock_costing import CostTake
from accounting.models.stock import (
    StockClaimAllocation,
    StockCostAllocation,
    StockCostLayer,
    StockMovement,
    StockMovementUnit,
    StockOpeningBridge,
    StockOriginAllocation,
    StockOriginClaim,
    StockPosition,
    StockPosting,
    StockSourceClaim,
    StockValueEntry,
)
from accounting.tasks.stock_ledger import EMPTY, ZERO, Cohort, Leg, PhysicalUnit, StockLedger
from accounting.tasks.stock_ordering import assert_committed, committed_generation, generation


async def guard(ledger: StockLedger, original: StockPosting) -> tuple[StockMovement, ...]:
    db = ledger.db
    if (
        original.company_id != ledger.posting.company_id
        or original.action == "REVERSAL"
        or original.stock_date > ledger.posting.stock_date
    ):
        raise ConflictError("stock reversal must follow an original posting in this company")
    previous = await db.scalar(
        select(StockPosting.id)
        .where(
            StockPosting.company_id == original.company_id,
            StockPosting.reverses_id == original.id,
            StockPosting.id != ledger.posting.id,
        )
        .limit(1)
    )
    if previous:
        raise ConflictError("stock posting already has a compensating reversal")
    movements = tuple(
        await db.scalars(
            select(StockMovement)
            .where(
                StockMovement.company_id == original.company_id,
                StockMovement.posting_id == original.id,
            )
            .order_by(StockMovement.id.desc())
            .with_for_update()
        )
    )
    if not movements:
        raise ConflictError("original physical posting evidence is unavailable")
    await assert_committed(db, original.company_id, pending=ledger.posting.id)
    committed = await committed_generation(db, original)
    later = (
        generation(StockPosting) > committed
        if committed is not None
        else StockPosting.id > original.id
    )
    cancelled = aliased(StockPosting)
    dependency = await db.scalar(
        select(StockPosting.id)
        .join(
            StockMovement,
            StockMovement.posting_id == StockPosting.id,
        )
        .outerjoin(
            cancelled,
            (cancelled.company_id == StockPosting.company_id)
            & (cancelled.reverses_id == StockPosting.id),
        )
        .where(
            StockPosting.company_id == original.company_id,
            or_(later, generation(StockPosting).is_(None) & (StockPosting.id > original.id)),
            StockPosting.id != original.id,
            StockPosting.id != ledger.posting.id,
            StockPosting.reverses_id.is_(None),
            cancelled.id.is_(None),
            StockMovement.pool_id.in_({movement.pool_id for movement in movements}),
        )
        .limit(1)
    )
    if dependency:
        raise ConflictError("reverse later dependent warehouse stock postings first")
    return movements


async def unwind_claims(ledger: StockLedger, original: StockMovement) -> None:
    db = ledger.db
    allocations = tuple(
        await db.scalars(
            select(StockClaimAllocation).where(
                StockClaimAllocation.company_id == ledger.posting.company_id,
                StockClaimAllocation.movement_id == original.id,
                StockClaimAllocation.claim_type.in_(("RETURN", "TRANSFER", "INVOICE")),
            )
        )
    )
    for allocation in allocations:
        counter = await db.scalar(
            select(StockSourceClaim)
            .where(
                StockSourceClaim.company_id == ledger.posting.company_id,
                StockSourceClaim.movement_id == allocation.source_movement_id,
                StockSourceClaim.claim_type == allocation.claim_type,
            )
            .with_for_update()
        )
        if (
            counter is None
            or counter.quantity < allocation.quantity
            or counter.value < allocation.value
        ):
            raise ConflictError(
                "source claim projection does not reconcile to its immutable allocation"
            )
        counter.quantity -= allocation.quantity
        counter.value -= allocation.value
        ledger.changed(counter)
        origins = await db.scalars(
            select(StockOriginAllocation).where(
                StockOriginAllocation.company_id == ledger.posting.company_id,
                StockOriginAllocation.movement_id == original.id,
            )
        )
        for origin in origins:
            origin_counter = await db.scalar(
                select(StockOriginClaim)
                .where(
                    StockOriginClaim.company_id == ledger.posting.company_id,
                    StockOriginClaim.source_movement_id == allocation.source_movement_id,
                    StockOriginClaim.origin_id == origin.origin_id,
                    StockOriginClaim.claim_type == allocation.claim_type,
                )
                .with_for_update()
            )
            if origin_counter is None or origin_counter.quantity < abs(origin.quantity):
                raise ConflictError("source cohort claim projection cannot be reversed")
            origin_counter.quantity -= abs(origin.quantity)
            ledger.changed(origin_counter)


async def reverse_leg(
    ledger: StockLedger,
    original: StockMovement,
    item: StockItemFact,
    warehouse: StockWarehouseFact,
) -> Leg:
    db = ledger.db
    position = await ledger.scoped(StockPosition, original.position_id)
    if (position.item_id, position.warehouse_id) != (item.item_id, warehouse.warehouse_id):
        raise ConflictError(
            "stock reversal source facts differ from the original physical position"
        )
    members = tuple(
        await db.scalars(
            select(StockMovementUnit)
            .where(
                StockMovementUnit.company_id == ledger.posting.company_id,
                StockMovementUnit.movement_id == original.id,
            )
            .order_by(StockMovementUnit.id)
        )
    )
    line = StockLine(
        line_id=original.line_id,
        item_id=item.item_id,
        warehouse_id=warehouse.warehouse_id,
        bin_id=position.bin_id,
        lot_id=position.lot_id,
        unit_ids=tuple(member.unit_id for member in members),
        quantity=abs(original.quantity),
    )
    units = await ledger.validate_tracking(line, item, outward=False)
    _, balance = await ledger.position(line, warehouse)
    pool = await ledger.pool(item, warehouse.warehouse_id)
    if original.pool_id != pool.id:
        raise ConflictError("stock reversal cannot replace its original warehouse cost pool")
    retained_value = await db.scalar(
        select(StockValueEntry).where(
            StockValueEntry.company_id == ledger.posting.company_id,
            StockValueEntry.movement_id == original.id,
        )
    )
    if retained_value is None:
        raise ConflictError("original carrying value is unavailable")
    origins = tuple(
        Cohort(row.origin_id, abs(row.quantity))
        for row in await db.scalars(
            select(StockOriginAllocation).where(
                StockOriginAllocation.company_id == ledger.posting.company_id,
                StockOriginAllocation.movement_id == original.id,
            )
        )
    )
    unit_values = tuple(
        PhysicalUnit(member.unit_id, member.origin_id, member.carrying_value) for member in members
    )
    states = await ledger.unit_positions(units)
    inward = original.quantity < 0
    for unit in units:
        state = states.get(unit.id)
        expected_position = None if inward else position.id
        if state is None or state.position_id != expected_position:
            raise ConflictError("serial custody no longer matches the original stock posting")
    movement = ledger.add(
        StockMovement,
        posting_id=ledger.posting.id,
        position_id=position.id,
        pool_id=pool.id,
        line_id=original.line_id,
        leg="IN" if inward else "OUT",
        quantity=-original.quantity,
        source_movement_id=original.id,
    )
    await db.flush()
    costs = []
    if pool.method == "FIFO":
        if inward:
            allocations = tuple(
                await db.scalars(
                    select(StockCostAllocation).where(
                        StockCostAllocation.company_id == ledger.posting.company_id,
                        StockCostAllocation.movement_id == original.id,
                    )
                )
            )
            for allocation in allocations:
                if allocation.layer_id is None:
                    raise ConflictError("original FIFO issue has no retained layer allocation")
                layer = await ledger.scoped(StockCostLayer, allocation.layer_id)
                layer.remaining_quantity += allocation.quantity
                layer.remaining_value += allocation.value
                ledger.changed(layer)
                costs.append(CostTake(layer.id, allocation.quantity, allocation.value))
        else:
            layers = tuple(
                await db.scalars(
                    select(StockCostLayer)
                    .where(
                        StockCostLayer.company_id == ledger.posting.company_id,
                        StockCostLayer.movement_id == original.id,
                    )
                    .with_for_update()
                )
            )
            if layers:
                costs = [CostTake(layer.id, layer.quantity, layer.value) for layer in layers]
            elif original.source_movement_id:
                # A bin-only transfer restored the original pool's existing layers.
                paired = await ledger.scoped(StockMovement, original.source_movement_id)
                if paired.posting_id != original.posting_id or paired.pool_id != original.pool_id:
                    raise ConflictError("original inward FIFO layer evidence is unavailable")
                costs = [
                    CostTake(row.layer_id, row.quantity, row.value)
                    for row in await db.scalars(
                        select(StockCostAllocation).where(
                            StockCostAllocation.company_id == ledger.posting.company_id,
                            StockCostAllocation.movement_id == paired.id,
                        )
                    )
                    if row.layer_id is not None
                ]
            for consumed in costs:
                layer = await ledger.scoped(StockCostLayer, consumed.identity)
                if (
                    layer.remaining_quantity < consumed.quantity
                    or layer.remaining_value < consumed.value
                ):
                    raise ConflictError("original inward costs have been consumed by later stock")
                layer.remaining_quantity -= consumed.quantity
                layer.remaining_value -= consumed.value
                ledger.changed(layer)
                ledger.add(
                    StockCostAllocation,
                    movement_id=movement.id,
                    pool_id=pool.id,
                    layer_id=layer.id,
                    layer_key=layer.id,
                    quantity=consumed.quantity,
                    value=consumed.value,
                )
    else:
        costs = [CostTake(pool.id, abs(original.quantity), abs(retained_value.amount))]
        if not inward:
            ledger.add(
                StockCostAllocation,
                movement_id=movement.id,
                pool_id=pool.id,
                layer_id=None,
                layer_key=EMPTY,
                quantity=abs(original.quantity),
                value=abs(retained_value.amount),
            )
    if sum((cost.quantity for cost in costs), ZERO) != abs(original.quantity) or sum(
        (cost.value for cost in costs), ZERO
    ) != abs(retained_value.amount):
        raise ConflictError("original stock cost allocations do not reconcile")
    await ledger.origin_change(movement, origins, inward=inward)
    await ledger.write_units(movement, unit_values, states, inward=inward)
    original_posting = await ledger.scoped(StockPosting, original.posting_id)
    if not inward and original_posting.action in {"RECEIPT", "OPENING"}:
        for state in states.values():
            state.origin_id = None  # Full receipt reversal restores the prepared identity.
    entry = await ledger.record_value(movement, pool, balance, -retained_value.amount)
    await unwind_claims(ledger, original)
    ledger.add(
        StockSourceClaim,
        movement_id=original.id,
        claim_type="REVERSAL",
        quantity=abs(original.quantity),
        value=abs(retained_value.amount),
    )
    for origin in origins:
        ledger.add(
            StockOriginClaim,
            source_movement_id=original.id,
            origin_id=origin.origin_id,
            claim_type="REVERSAL",
            quantity=origin.quantity,
        )
    ledger.add(
        StockClaimAllocation,
        source_movement_id=original.id,
        movement_id=movement.id,
        claim_type="REVERSAL",
        quantity=abs(original.quantity),
        value=abs(retained_value.amount),
    )
    for bridge in await db.scalars(
        select(StockOpeningBridge).where(
            StockOpeningBridge.company_id == ledger.posting.company_id,
            StockOpeningBridge.value_entry_id == retained_value.id,
        )
    ):
        ledger.add(
            StockOpeningBridge,
            value_entry_id=entry.id,
            journal_line_id=bridge.journal_line_id,
            amount=bridge.amount,
        )
    await db.flush()
    return Leg(
        movement.id,
        entry.id,
        position.id,
        pool.id,
        -original.quantity,
        -retained_value.amount,
        origins,
        unit_values,
        tuple(costs),
    )
