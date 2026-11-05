"""Guarded partial claims against immutable native physical source movements."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from billing_platform.errors import ConflictError
from sqlalchemy import select
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact, StockWarehouseFact

from accounting.domain.stock_costing import CostBucket, linked_return
from accounting.models.stock import (
    StockClaimAllocation,
    StockMovement,
    StockMovementUnit,
    StockOriginAllocation,
    StockOriginBalance,
    StockOriginClaim,
    StockPosition,
    StockPosting,
    StockSourceClaim,
    StockUnitPosition,
    StockValueEntry,
)
from accounting.tasks.stock_ledger import ZERO, Cohort, Leg, PhysicalUnit, StockLedger


@dataclass(frozen=True)
class SourceClaim:
    source: StockMovement
    posting: StockPosting
    counter: StockSourceClaim
    origin_counters: tuple[StockOriginClaim, ...]
    origins: tuple[Cohort, ...]
    units: tuple[PhysicalUnit, ...]
    value: Decimal


async def claim(
    ledger: StockLedger,
    line: StockLine,
    *,
    claim_type: str,
    source_action: str,
    source_leg: str,
    available_position_id: uuid.UUID | None = None,
) -> SourceClaim:
    if line.source_movement_id is None:
        raise ConflictError("linked stock requires its original native source movement")
    db = ledger.db
    source = await ledger.scoped(StockMovement, line.source_movement_id)
    posting = await ledger.scoped(StockPosting, source.posting_id)
    position = await ledger.scoped(StockPosition, source.position_id)
    if (
        posting.action != source_action
        or source.leg != source_leg
        or posting.stock_date > ledger.posting.stock_date
        or posting.currency != ledger.posting.currency
        or position.item_id != line.item_id
        or position.lot_id != line.lot_id
        or await db.scalar(
            select(StockPosting.id)
            .where(
                StockPosting.company_id == ledger.posting.company_id,
                StockPosting.reverses_id == posting.id,
            )
            .limit(1)
        )
    ):
        raise ConflictError("original stock source is not eligible for this claim")
    value_entry = await db.scalar(
        select(StockValueEntry).where(
            StockValueEntry.company_id == ledger.posting.company_id,
            StockValueEntry.movement_id == source.id,
        )
    )
    if value_entry is None:
        raise ConflictError("original stock source has no retained carrying value")
    counter = await db.scalar(
        select(StockSourceClaim)
        .where(
            StockSourceClaim.company_id == ledger.posting.company_id,
            StockSourceClaim.movement_id == source.id,
            StockSourceClaim.claim_type == claim_type,
        )
        .with_for_update()
    )
    if counter is None:
        counter = ledger.add(
            StockSourceClaim,
            movement_id=source.id,
            claim_type=claim_type,
            quantity=ZERO,
            value=ZERO,
        )
    assigned = linked_return(
        CostBucket(source.id, abs(source.quantity), abs(value_entry.amount)),
        counter.quantity,
        counter.value,
        line.quantity,
        places=ledger.places,
        rounding=ledger.rounding,
    )
    units: tuple[PhysicalUnit, ...] = ()
    selected_origins: dict[uuid.UUID, Decimal] = {}
    if line.unit_ids:
        members = list(
            await db.scalars(
                select(StockMovementUnit).where(
                    StockMovementUnit.company_id == ledger.posting.company_id,
                    StockMovementUnit.movement_id == source.id,
                    StockMovementUnit.unit_id.in_(line.unit_ids),
                )
            )
        )
        if len(members) != len(line.unit_ids):
            raise ConflictError("selected serials do not belong to this original movement")
        mapping = {member.unit_id: member for member in members}
        units = tuple(
            PhysicalUnit(identity, mapping[identity].origin_id, mapping[identity].carrying_value)
            for identity in line.unit_ids
        )
        states = list(
            await db.scalars(
                select(StockUnitPosition)
                .where(
                    StockUnitPosition.company_id == ledger.posting.company_id,
                    StockUnitPosition.unit_id.in_(line.unit_ids),
                )
                .with_for_update()
            )
        )
        if len(states) != len(units):
            raise ConflictError("serial source custody is unavailable")
        for state in states:
            if source_leg == "OUT":
                if state.position_id is not None:
                    raise ConflictError(
                        "serial is no longer awaiting return from this original issue"
                    )
                if state.last_movement_id != source.id:
                    last = await ledger.scoped(StockMovement, state.last_movement_id)
                    last_posting = await ledger.scoped(StockPosting, last.posting_id)
                    restored = await db.scalar(
                        select(StockClaimAllocation.id)
                        .where(
                            StockClaimAllocation.company_id == ledger.posting.company_id,
                            StockClaimAllocation.movement_id == last.source_movement_id,
                            StockClaimAllocation.source_movement_id == source.id,
                            StockClaimAllocation.claim_type == "RETURN",
                        )
                        .limit(1)
                    )
                    if not last_posting.reverses_id or last.leg != "OUT" or not restored:
                        raise ConflictError(
                            "serial is no longer awaiting return from this original issue"
                        )
            if available_position_id is not None and state.position_id != available_position_id:
                raise ConflictError("serial is not available at the claimed physical position")
        for member in units:
            selected_origins[member.origin_id] = selected_origins.get(member.origin_id, ZERO) + 1
        value = sum((member.carrying_value for member in units), ZERO)
        if counter.value + value > abs(value_entry.amount):
            raise ConflictError("serial claim exceeds its original carrying value")
    else:
        value = assigned.value
    remaining = line.quantity
    origins = []
    counters = []
    after: uuid.UUID | None = None
    while remaining:
        query = select(StockOriginAllocation).where(
            StockOriginAllocation.company_id == ledger.posting.company_id,
            StockOriginAllocation.movement_id == source.id,
        )
        if after:
            query = query.where(StockOriginAllocation.id > after)
        rows = list(await db.scalars(query.order_by(StockOriginAllocation.id).limit(200)))
        if not rows:
            raise ConflictError("original physical receipt cohorts do not cover this claim")
        for allocation in rows:
            origin_counter = await db.scalar(
                select(StockOriginClaim)
                .where(
                    StockOriginClaim.company_id == ledger.posting.company_id,
                    StockOriginClaim.source_movement_id == source.id,
                    StockOriginClaim.origin_id == allocation.origin_id,
                    StockOriginClaim.claim_type == claim_type,
                )
                .with_for_update()
            )
            consumed = origin_counter.quantity if origin_counter else ZERO
            available = abs(allocation.quantity) - consumed
            if available < 0:
                raise ConflictError("original cohort claim counters do not reconcile")
            if available_position_id is not None:
                stock_quantity = await db.scalar(
                    select(StockOriginBalance.quantity)
                    .where(
                        StockOriginBalance.company_id == ledger.posting.company_id,
                        StockOriginBalance.position_id == available_position_id,
                        StockOriginBalance.origin_id == allocation.origin_id,
                    )
                    .with_for_update()
                )
                available = min(available, stock_quantity or ZERO)
            requested = (
                selected_origins.get(allocation.origin_id, ZERO)
                if units
                else min(available, remaining)
            )
            if requested > available:
                raise ConflictError(
                    "selected serials exceed their unclaimed original receipt cohort"
                )
            if requested:
                if origin_counter is None:
                    origin_counter = ledger.add(
                        StockOriginClaim,
                        source_movement_id=source.id,
                        origin_id=allocation.origin_id,
                        claim_type=claim_type,
                        quantity=ZERO,
                    )
                origins.append(Cohort(allocation.origin_id, requested))
                counters.append(origin_counter)
                remaining -= requested
            if not remaining:
                break
        after = rows[-1].id
    return SourceClaim(source, posting, counter, tuple(counters), tuple(origins), units, value)


def consume(
    ledger: StockLedger, source: SourceClaim, requested: Decimal, movement_id: uuid.UUID
) -> None:
    ledger.add(
        StockClaimAllocation,
        source_movement_id=source.source.id,
        movement_id=movement_id,
        claim_type=source.counter.claim_type,
        quantity=requested,
        value=source.value,
    )
    source.counter.quantity += requested
    source.counter.value += source.value
    ledger.changed(source.counter)
    for counter, allocation in zip(source.origin_counters, source.origins, strict=True):
        counter.quantity += allocation.quantity
        ledger.changed(counter)


async def customer_return(
    ledger: StockLedger, line: StockLine, item: StockItemFact, warehouse: StockWarehouseFact
) -> tuple[Leg, SourceClaim]:
    source = await claim(
        ledger, line, claim_type="RETURN", source_action="DISPATCH", source_leg="OUT"
    )
    received = await ledger.receive(
        line,
        item,
        warehouse,
        value=source.value,
        origins=source.origins,
        unit_values=source.units if item.serial_tracking else None,
        source_movement_id=source.source.id,
    )
    consume(ledger, source, line.quantity, received.movement_id)
    await ledger.db.flush()
    return received, source


async def supplier_return(
    ledger: StockLedger, line: StockLine, item: StockItemFact, warehouse: StockWarehouseFact
) -> tuple[Leg, SourceClaim]:
    position, _ = await ledger.position(line, warehouse)
    source = await claim(
        ledger,
        line,
        claim_type="RETURN",
        source_action="RECEIPT",
        source_leg="IN",
        available_position_id=position.id,
    )
    issued = await ledger.issue(
        line,
        item,
        warehouse,
        origins=source.origins,
        source_movement_id=source.source.id,
    )
    consume(ledger, source, line.quantity, issued.movement_id)
    await ledger.db.flush()
    return issued, source
