"""Local physical effects composed by the common voucher execution transaction.

This module never commits, performs I/O to another owner, trusts browser source
facts, or chooses a financial account. Its caller holds the company setup lock,
has checked the native source fence and fiscal/Identity posting authority, and
rolls back every effect if journal or execution reconciliation fails.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypeVar

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode
from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact, StockWarehouseFact

from accounting.domain.stock_costing import CostBucket, CostTake, exact, fifo, take
from accounting.domain.stock_eligibility import issue_eligible, posting_day, quantity
from accounting.domain.stock_tracking import validate_dates, validate_identifiers
from accounting.models.masters import Record
from accounting.models.stock import (
    StockBalance,
    StockCostAllocation,
    StockCostLayer,
    StockCostPool,
    StockCostPoolEvent,
    StockMoneyRecord,
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
from accounting.schemas.stock_tracking import IdentifierInput, TrackingSource
from accounting.tasks.stock_ordering import movement_generation
from accounting.tasks.stock_selection import candidates, require_order

ZERO = Decimal("0.0000")
EMPTY = uuid.UUID(int=0)
Row = TypeVar("Row", bound=Record)


@dataclass(frozen=True)
class Cohort:
    origin_id: uuid.UUID
    quantity: Decimal


@dataclass(frozen=True)
class PhysicalUnit:
    unit_id: uuid.UUID
    origin_id: uuid.UUID
    carrying_value: Decimal


@dataclass(frozen=True)
class Leg:
    movement_id: uuid.UUID
    value_entry_id: uuid.UUID
    position_id: uuid.UUID
    pool_id: uuid.UUID
    quantity: Decimal
    value: Decimal
    origins: tuple[Cohort, ...]
    units: tuple[PhysicalUnit, ...]
    costs: tuple[CostTake, ...]


class StockLedger:
    """A single local transaction; projections are not independent authorities."""

    def __init__(
        self,
        db: AsyncSession,
        posting: StockPosting,
        *,
        actor_id: uuid.UUID,
        timezone: str,
        places: int,
        rounding: RoundingMode,
        now: dt.datetime | None = None,
    ) -> None:
        self.db = db
        self.posting = posting
        self.actor_id = actor_id
        self.timezone = timezone
        self.places = places
        self.rounding = rounding
        self.now = now or utcnow()
        self.created: list[Record] = []
        self.observed: dict[tuple[str, uuid.UUID], tuple[Record, int]] = {}

    def add(self, model: type[Row], **values: Any) -> Row:
        if issubclass(model, StockMoneyRecord):
            values["currency"] = self.posting.currency
        row = model(
            id=uuid7(),
            tenant_id=self.posting.tenant_id,
            company_id=self.posting.company_id,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            row_version=1,
            **values,
        )
        self.db.add(row)
        self.created.append(row)
        return row

    def observe(self, row: Record) -> None:
        if row not in self.created:
            self.observed.setdefault((row.__tablename__, row.id), (row, row.row_version))

    def changed(self, row: Record) -> None:
        self.observe(row)
        row.row_version += 1
        row.updated_by = self.actor_id

    async def scoped(self, model: type[Row], identity: uuid.UUID) -> Row:
        row = await self.db.scalar(
            select(model)
            .where(model.company_id == self.posting.company_id, model.id == identity)
            .with_for_update()
        )
        if row is None:
            raise ConflictError("stock reference is unavailable in this company")
        self.observe(row)
        return row

    async def position(
        self, line: StockLine, warehouse: StockWarehouseFact
    ) -> tuple[StockPosition, StockBalance]:
        if not warehouse.is_active or warehouse.warehouse_id != line.warehouse_id:
            raise ConflictError("stock warehouse is unavailable")
        position = await self.db.scalar(
            select(StockPosition)
            .where(
                StockPosition.company_id == self.posting.company_id,
                StockPosition.item_id == line.item_id,
                StockPosition.warehouse_id == line.warehouse_id,
                StockPosition.bin_key == (line.bin_id or EMPTY),
                StockPosition.lot_key == (line.lot_id or EMPTY),
                StockPosition.disposition == "USABLE",
            )
            .with_for_update()
        )
        if position is None:
            position = self.add(
                StockPosition,
                item_id=line.item_id,
                warehouse_id=line.warehouse_id,
                bin_id=line.bin_id,
                bin_key=line.bin_id or EMPTY,
                lot_id=line.lot_id,
                lot_key=line.lot_id or EMPTY,
                owner_kind="COMPANY",
                custody_kind="TRANSIT" if warehouse.kind == "INTERNAL_TRANSIT" else "WAREHOUSE",
                disposition="USABLE",
            )
            await self.db.flush()
        balance = await self.db.scalar(
            select(StockBalance)
            .where(
                StockBalance.company_id == self.posting.company_id,
                StockBalance.position_id == position.id,
            )
            .with_for_update()
        )
        if balance is None:
            balance = self.add(StockBalance, position_id=position.id, quantity=ZERO)
            await self.db.flush()
        return position, balance

    async def pool(self, item: StockItemFact, warehouse_id: uuid.UUID) -> StockCostPool:
        if item.valuation_method not in {"FIFO", "MOVING_AVERAGE"}:
            raise ValidationFailedError(
                "this stock profile requires a native specific-cost adapter"
            )
        pool = await self.db.scalar(
            select(StockCostPool)
            .where(
                StockCostPool.company_id == self.posting.company_id,
                StockCostPool.item_id == item.item_id,
                StockCostPool.warehouse_id == warehouse_id,
            )
            .with_for_update()
        )
        if pool is None:
            pool = self.add(
                StockCostPool,
                item_id=item.item_id,
                warehouse_id=warehouse_id,
                method=item.valuation_method,
                quantity=ZERO,
                value=ZERO,
            )
            await self.db.flush()
        if pool.currency != self.posting.currency:
            raise ConflictError("warehouse carrying-value currency differs from this posting")
        if pool.method != item.valuation_method:
            raise ConflictError("warehouse valuation method differs from its retained cost pool")
        posting_day(
            self.posting.stock_date,
            now=self.now,
            timezone=self.timezone,
            last_posted_day=pool.last_stock_date,
        )
        return pool

    async def validate_tracking(
        self, line: StockLine, item: StockItemFact, *, outward: bool
    ) -> tuple[StockUnit, ...]:
        if line.item_id != item.item_id:
            raise ConflictError("stock item differs from its native source facts")
        quantity(line.quantity, increment=item.quantity_increment, serialized=item.serial_tracking)
        quantum = Decimal(1).scaleb(-item.quantity_decimal_places)
        if line.quantity != line.quantity.quantize(quantum):
            raise ValidationFailedError("quantity exceeds the base unit's decimal precision")
        if item.lot_tracking != (line.lot_id is not None):
            raise ValidationFailedError(
                "stock batch selection differs from the item's active profile"
            )
        if item.serial_tracking:
            if len(line.unit_ids) != line.quantity:
                raise ValidationFailedError(
                    "select exactly one prepared serial for every physical unit"
                )
        elif line.unit_ids:
            raise ValidationFailedError("this item does not allow serial selection")
        if line.lot_id:
            lot = await self.scoped(StockLot, line.lot_id)
            prepared = self.preparation(lot, item)
            validate_dates(prepared, lot.manufactured_on, lot.expires_on)
            if lot.item_id != line.item_id:
                raise ConflictError("batch belongs to another product")
            if lot.status != "ACTIVE" or lot.is_held:
                raise ConflictError("held or retired batches cannot move stock")
            if item.expiry_required and lot.expires_on is None:
                raise ConflictError("batch expiry is required by its active product profile")
            if item.manufacture_date_required and lot.manufactured_on is None:
                raise ConflictError(
                    "batch manufacture date is required by its active product profile"
                )
            if lot.manufactured_on and self.posting.stock_date < lot.manufactured_on:
                raise ConflictError("stock cannot move before its manufacture date")
            if self.posting.action == "OPENING":
                if lot.expires_on and lot.expires_on < self.posting.stock_date:
                    raise ConflictError(
                        "expired opening stock requires an unsupported quarantine disposition"
                    )
                if (
                    line.opening
                    and line.opening.received_on
                    and lot.manufactured_on
                    and line.opening.received_on < lot.manufactured_on
                ):
                    raise ConflictError("opening receipt history cannot precede batch manufacture")
            if outward:
                issue_eligible(
                    day=self.posting.stock_date,
                    active=True,
                    held=False,
                    manufactured_on=lot.manufactured_on,
                    expires_on=lot.expires_on,
                    minimum_remaining_life_days=item.minimum_remaining_life_days,
                )
        selected = (
            list(
                await self.db.scalars(
                    select(StockUnit)
                    .where(
                        StockUnit.company_id == self.posting.company_id,
                        StockUnit.id.in_(line.unit_ids),
                    )
                    .with_for_update()
                )
            )
            if line.unit_ids
            else []
        )
        if {unit.id for unit in selected} != set(line.unit_ids):
            raise ConflictError("serial reference is unavailable in this company")
        by_id = {unit.id: unit for unit in selected}
        identifier_rows: dict[uuid.UUID, list[StockUnitIdentifier]] = {}
        if selected:
            for identifier in await self.db.scalars(
                select(StockUnitIdentifier)
                .where(
                    StockUnitIdentifier.company_id == self.posting.company_id,
                    StockUnitIdentifier.unit_id.in_(line.unit_ids),
                )
                .order_by(StockUnitIdentifier.id)
            ):
                self.observe(identifier)
                identifier_rows.setdefault(identifier.unit_id, []).append(identifier)
        units = []
        for identity in line.unit_ids:
            unit = by_id[identity]
            self.observe(unit)
            prepared = self.preparation(unit, item)
            retained = identifier_rows.get(identity, [])
            validated = validate_identifiers(
                prepared,
                [
                    IdentifierInput.model_validate(
                        {
                            "identifier_type": entry.identifier_type,
                            "slot": entry.slot,
                            "value": entry.value,
                        }
                    )
                    for entry in retained
                ],
            )
            if any(
                entry.normalization_version != prepared.normalization_version
                or entry.normalized_value != key
                or entry.namespace_key != namespace
                for entry, (_, key, namespace) in zip(retained, validated, strict=True)
            ):
                raise ConflictError(
                    "serial tracking identifiers differ from their prepared evidence"
                )
            if unit.item_id != line.item_id or unit.lot_id != line.lot_id:
                raise ConflictError("serial belongs to another product or batch")
            if unit.status != "ACTIVE" or unit.is_held:
                raise ConflictError("held or retired serials cannot move stock")
            units.append(unit)
        return tuple(units)

    def preparation(self, row: StockLot | StockUnit, item: StockItemFact) -> TrackingSource:
        try:
            prepared = TrackingSource.model_validate(row.source_facts)
        except ValidationError as exc:
            raise ConflictError(
                "complete verified tracking preparation before moving this identity"
            ) from exc
        if (
            prepared.company_id,
            prepared.item_id,
            prepared.profile_revision_id,
            prepared.lot_tracking,
            prepared.serial_tracking,
            prepared.expiry_required,
            prepared.manufacture_date_required,
        ) != (
            self.posting.company_id,
            item.item_id,
            item.profile_revision_id,
            item.lot_tracking,
            item.serial_tracking,
            item.expiry_required,
            item.manufacture_date_required,
        ):
            raise ConflictError(
                "prepared tracking definitions differ from the active product profile"
            )
        return prepared

    async def origin_change(
        self, movement: StockMovement, origins: tuple[Cohort, ...], *, inward: bool
    ) -> None:
        if len({entry.origin_id for entry in origins}) != len(origins):
            raise ConflictError("physical origin allocation must be consolidated")
        if sum((entry.quantity for entry in origins), ZERO) != abs(movement.quantity):
            raise ConflictError("physical origins do not reconcile to movement quantity")
        for entry in origins:
            exact(entry.quantity, positive=True)
            origin = await self.scoped(StockReceiptOrigin, entry.origin_id)
            source = await self.scoped(StockMovement, origin.movement_id)
            source_position = await self.scoped(StockPosition, source.position_id)
            position = await self.scoped(StockPosition, movement.position_id)
            if (source_position.item_id, source_position.lot_id) != (
                position.item_id,
                position.lot_id,
            ):
                raise ConflictError("physical origin belongs to another product or batch")
            balance = await self.db.scalar(
                select(StockOriginBalance)
                .where(
                    StockOriginBalance.company_id == self.posting.company_id,
                    StockOriginBalance.origin_id == entry.origin_id,
                    StockOriginBalance.position_id == movement.position_id,
                )
                .with_for_update()
            )
            if balance is None:
                balance = self.add(
                    StockOriginBalance,
                    origin_id=entry.origin_id,
                    position_id=movement.position_id,
                    quantity=ZERO,
                )
            signed = entry.quantity if inward else -entry.quantity
            if balance.quantity + signed < 0:
                raise ConflictError("selected physical receipt origin has insufficient stock")
            balance.quantity = exact(balance.quantity + signed)
            self.changed(balance)
            self.add(
                StockOriginAllocation,
                origin_id=entry.origin_id,
                movement_id=movement.id,
                quantity=signed,
            )

    async def available_origins(
        self, position_id: uuid.UUID, requested: Decimal
    ) -> tuple[Cohort, ...]:
        remaining = requested
        after: tuple[dt.date, int, uuid.UUID] | None = None
        receipt_order = movement_generation(self.posting.company_id, StockReceiptOrigin.movement_id)
        result = []
        while remaining:
            query = (
                select(StockOriginBalance, StockReceiptOrigin.received_on, receipt_order)
                .join(
                    StockReceiptOrigin,
                    and_(
                        StockReceiptOrigin.tenant_id == StockOriginBalance.tenant_id,
                        StockReceiptOrigin.company_id == StockOriginBalance.company_id,
                        StockReceiptOrigin.id == StockOriginBalance.origin_id,
                    ),
                )
                .where(
                    StockOriginBalance.company_id == self.posting.company_id,
                    StockOriginBalance.position_id == position_id,
                    StockOriginBalance.quantity > 0,
                )
            )
            if after:
                query = query.where(
                    or_(
                        StockReceiptOrigin.received_on > after[0],
                        and_(
                            StockReceiptOrigin.received_on == after[0],
                            receipt_order > after[1],
                        ),
                        and_(
                            StockReceiptOrigin.received_on == after[0],
                            receipt_order == after[1],
                            StockOriginBalance.origin_id > after[2],
                        ),
                    )
                )
            rows = list(
                (
                    await self.db.execute(
                        query.order_by(
                            StockReceiptOrigin.received_on,
                            receipt_order,
                            StockOriginBalance.origin_id,
                        )
                        .limit(200)
                        .with_for_update()
                    )
                ).all()
            )
            if not rows:
                raise ConflictError("physical origin balance does not cover the stock issue")
            if any(ordinal is None for _, _, ordinal in rows):
                raise ConflictError("physical receipt committed owner order is unavailable")
            for row, _received_on, _ordinal in rows:
                consumed = min(row.quantity, remaining)
                result.append(Cohort(row.origin_id, consumed))
                remaining -= consumed
                if not remaining:
                    break
            after = (rows[-1][1], rows[-1][2], rows[-1][0].origin_id)
        return tuple(result)

    async def unit_positions(
        self, units: tuple[StockUnit, ...]
    ) -> dict[uuid.UUID, StockUnitPosition]:
        if not units:
            return {}
        rows = await self.db.scalars(
            select(StockUnitPosition)
            .where(
                StockUnitPosition.company_id == self.posting.company_id,
                StockUnitPosition.unit_id.in_([unit.id for unit in units]),
            )
            .with_for_update()
        )
        return {row.unit_id: row for row in rows}

    async def cost_out(
        self,
        pool: StockCostPool,
        requested: Decimal,
        *,
        source_movement_id: uuid.UUID | None = None,
        assigned_value: Decimal | None = None,
    ) -> tuple[CostTake, ...]:
        if requested > pool.quantity:
            raise ConflictError("insufficient warehouse stock; negative stock is blocked")
        if source_movement_id is not None:
            # A typed transit receipt consumes its own shipment's escrow, never a
            # different shipment or an average blended across pending transfers.
            layers = list(
                await self.db.scalars(
                    select(StockCostLayer)
                    .where(
                        StockCostLayer.company_id == self.posting.company_id,
                        StockCostLayer.pool_id == pool.id,
                        StockCostLayer.movement_id == source_movement_id,
                    )
                    .limit(2)
                    .with_for_update()
                )
            )
            if pool.method != "FIFO" or len(layers) != 1 or assigned_value is None:
                raise ConflictError("transit source cost escrow is unavailable")
            layer = layers[0]
            exact(assigned_value)
            if (
                requested > layer.remaining_quantity
                or assigned_value > layer.remaining_value
                or (
                    requested == layer.remaining_quantity
                    and assigned_value != layer.remaining_value
                )
            ):
                raise ConflictError("transit cost claim exceeds its retained shipment value")
            layer.remaining_quantity -= requested
            layer.remaining_value -= assigned_value
            self.changed(layer)
            return (CostTake(layer.id, requested, assigned_value),)
        if assigned_value is not None:
            raise ConflictError("only a linked transit receipt can select retained escrow cost")
        if pool.method == "MOVING_AVERAGE":
            return (
                take(
                    CostBucket(pool.id, pool.quantity, pool.value),
                    requested,
                    places=self.places,
                    rounding=self.rounding,
                ),
            )
        remaining = requested
        after: tuple[dt.date, int, uuid.UUID] | None = None
        receipt_order = movement_generation(self.posting.company_id, StockCostLayer.movement_id)
        allocations: list[CostTake] = []
        while remaining:
            query = select(StockCostLayer, receipt_order).where(
                StockCostLayer.company_id == self.posting.company_id,
                StockCostLayer.pool_id == pool.id,
                StockCostLayer.remaining_quantity > 0,
            )
            if after:
                query = query.where(
                    (StockCostLayer.received_on > after[0])
                    | ((StockCostLayer.received_on == after[0]) & (receipt_order > after[1]))
                    | (
                        (StockCostLayer.received_on == after[0])
                        & (receipt_order == after[1])
                        & (StockCostLayer.id > after[2])
                    )
                )
            page = (
                await self.db.execute(
                    query.order_by(StockCostLayer.received_on, receipt_order, StockCostLayer.id)
                    .limit(200)
                    .with_for_update()
                )
            ).all()
            if any(ordinal is None for _, ordinal in page):
                raise ConflictError("FIFO receipt committed owner order is unavailable")
            rows = [row for row, _ in page]
            if not rows:
                raise ConflictError("warehouse FIFO layers do not cover its stock quantity")
            batch_quantity = min(remaining, sum((row.remaining_quantity for row in rows), ZERO))
            consumed = fifo(
                [CostBucket(row.id, row.remaining_quantity, row.remaining_value) for row in rows],
                batch_quantity,
                places=self.places,
                rounding=self.rounding,
            )
            mapping = {row.id: row for row in rows}
            for entry in consumed:
                layer = mapping[entry.identity]
                layer.remaining_quantity -= entry.quantity
                layer.remaining_value -= entry.value
                self.changed(layer)
            allocations.extend(consumed)
            remaining -= batch_quantity
            after = (rows[-1].received_on, page[-1][1], rows[-1].id)
        return tuple(allocations)

    def split_units(
        self,
        units: tuple[StockUnit, ...],
        origins: dict[uuid.UUID, uuid.UUID],
        costs: tuple[CostTake, ...],
    ) -> tuple[PhysicalUnit, ...]:
        """Allocate actual warehouse cost slices, assigning every final residual."""
        if not units:
            return ()
        buckets = [CostBucket(entry.identity, entry.quantity, entry.value) for entry in costs]
        cursor = 0
        result = []
        for unit in units:
            remaining = Decimal(1)
            value = ZERO
            while remaining:
                if cursor == len(buckets):
                    raise ConflictError("serial cost allocation does not cover its physical units")
                bucket = buckets[cursor]
                consumed = take(
                    bucket,
                    min(remaining, bucket.quantity),
                    places=self.places,
                    rounding=self.rounding,
                )
                value += consumed.value
                remaining -= consumed.quantity
                buckets[cursor] = CostBucket(
                    bucket.identity,
                    bucket.quantity - consumed.quantity,
                    bucket.value - consumed.value,
                )
                if not buckets[cursor].quantity:
                    cursor += 1
            result.append(PhysicalUnit(unit.id, origins[unit.id], value))
        if any(bucket.quantity or bucket.value for bucket in buckets):
            raise ConflictError("serial cost allocation left an unexplained quantity or value")
        return tuple(result)

    async def write_units(
        self,
        movement: StockMovement,
        units: tuple[PhysicalUnit, ...],
        states: dict[uuid.UUID, StockUnitPosition],
        *,
        inward: bool,
    ) -> None:
        for unit in units:
            self.add(
                StockMovementUnit,
                movement_id=movement.id,
                unit_id=unit.unit_id,
                carrying_value=unit.carrying_value,
                origin_id=unit.origin_id,
            )
            state = states.get(unit.unit_id)
            if state is None:
                state = self.add(
                    StockUnitPosition,
                    unit_id=unit.unit_id,
                    position_id=movement.position_id if inward else None,
                    last_movement_id=movement.id,
                    origin_id=unit.origin_id,
                )
            else:
                state.position_id = movement.position_id if inward else None
                state.last_movement_id = movement.id
                state.origin_id = unit.origin_id
                self.changed(state)

    async def record_value(
        self,
        movement: StockMovement,
        pool: StockCostPool,
        balance: StockBalance,
        value: Decimal,
    ) -> StockValueEntry:
        before_quantity, before_value = pool.quantity, pool.value
        pool.quantity = exact(pool.quantity + movement.quantity)
        pool.value = exact(pool.value + value)
        if not pool.quantity and pool.value:
            raise ConflictError("an empty warehouse cost pool cannot retain unexplained value")
        balance.quantity = exact(balance.quantity + movement.quantity)
        pool.last_stock_date = self.posting.stock_date
        pool.last_posting_id = self.posting.id
        self.changed(pool)
        self.changed(balance)
        self.add(
            StockCostPoolEvent,
            pool_id=pool.id,
            movement_id=movement.id,
            method=pool.method,
            before_quantity=before_quantity,
            before_value=before_value,
            after_quantity=pool.quantity,
            after_value=pool.value,
        )
        entry = self.add(StockValueEntry, movement_id=movement.id, pool_id=pool.id, amount=value)
        await self.db.flush()
        return entry

    async def receive(
        self,
        line: StockLine,
        item: StockItemFact,
        warehouse: StockWarehouseFact,
        *,
        value: Decimal,
        origins: tuple[Cohort, ...] | None = None,
        unit_values: tuple[PhysicalUnit, ...] | None = None,
        source_movement_id: uuid.UUID | None = None,
        restore_costs: tuple[CostTake, ...] | None = None,
    ) -> Leg:
        exact(value)
        received_on = self.posting.stock_date
        if line.opening:
            if self.posting.action != "OPENING":
                raise ValidationFailedError("historical receipt evidence belongs only to openings")
            if line.opening.received_on:
                if line.opening.received_on > self.posting.stock_date:
                    raise ValidationFailedError("opening receipt age cannot follow the cutover")
                received_on = line.opening.received_on
        units = await self.validate_tracking(line, item, outward=False)
        position, balance = await self.position(line, warehouse)
        pool = await self.pool(item, line.warehouse_id)
        states = await self.unit_positions(units)
        for unit in units:
            state = states.get(unit.id)
            if state is not None and (
                state.position_id is not None or (origins is None and state.origin_id is not None)
            ):
                raise ConflictError(
                    "serial already has stock history; use a linked return or transfer"
                )
        movement = self.add(
            StockMovement,
            posting_id=self.posting.id,
            position_id=position.id,
            pool_id=pool.id,
            line_id=line.line_id,
            leg="IN",
            quantity=line.quantity,
            source_movement_id=source_movement_id,
        )
        await self.db.flush()
        if origins is None:
            origin = self.add(
                StockReceiptOrigin,
                movement_id=movement.id,
                received_on=received_on,
                history_known=line.opening.history_known
                if line.opening
                else self.posting.action not in {"OPENING", "COUNT"},
                quantity=line.quantity,
            )
            await self.db.flush()
            origins = (Cohort(origin.id, line.quantity),)
        await self.origin_change(movement, origins, inward=True)
        costs: tuple[CostTake, ...] = (CostTake(pool.id, line.quantity, value),)
        if pool.method == "FIFO":
            if restore_costs is not None:
                if (
                    sum((entry.quantity for entry in restore_costs), ZERO) != line.quantity
                    or sum((entry.value for entry in restore_costs), ZERO) != value
                ):
                    raise ConflictError("restored warehouse layers differ from the transfer cost")
                for entry in restore_costs:
                    layer = await self.scoped(StockCostLayer, entry.identity)
                    if layer.pool_id != pool.id:
                        raise ConflictError("same-pool restoration cannot change warehouses")
                    layer.remaining_quantity += entry.quantity
                    layer.remaining_value += entry.value
                    self.changed(layer)
                costs = restore_costs
            else:
                layer = self.add(
                    StockCostLayer,
                    pool_id=pool.id,
                    movement_id=movement.id,
                    sequence=1,
                    received_on=received_on,
                    quantity=line.quantity,
                    value=value,
                    remaining_quantity=line.quantity,
                    remaining_value=value,
                )
                await self.db.flush()
                costs = (CostTake(layer.id, line.quantity, value),)
        if units:
            if unit_values is None:
                if len(origins) != 1:
                    raise ConflictError(
                        "received serials require their exact retained physical origins"
                    )
                unit_values = self.split_units(
                    units, {unit.id: origins[0].origin_id for unit in units}, costs
                )
            expected = Counter({origin.origin_id: origin.quantity for origin in origins})
            actual = Counter(unit.origin_id for unit in unit_values)
            if (
                {entry.unit_id for entry in unit_values} != {unit.id for unit in units}
                or actual != expected
                or sum((unit.carrying_value for unit in unit_values), ZERO) != value
            ):
                raise ConflictError(
                    "received serials do not reconcile to their physical origins and carrying value"
                )
            await self.write_units(movement, unit_values, states, inward=True)
        elif unit_values:
            raise ConflictError("non-serialized stock cannot carry physical serial cost facts")
        value_entry = await self.record_value(movement, pool, balance, value)
        return Leg(
            movement.id,
            value_entry.id,
            position.id,
            pool.id,
            line.quantity,
            value,
            origins,
            unit_values or (),
            costs,
        )

    async def issue(
        self,
        line: StockLine,
        item: StockItemFact,
        warehouse: StockWarehouseFact,
        *,
        origins: tuple[Cohort, ...] | None = None,
        source_movement_id: uuid.UUID | None = None,
        transit_source_id: uuid.UUID | None = None,
        transit_units: tuple[PhysicalUnit, ...] | None = None,
        transit_value: Decimal | None = None,
        count_adjustment: bool = False,
    ) -> Leg:
        if count_adjustment and self.posting.action != "COUNT":
            raise ConflictError("count origin selection belongs only to a native count posting")
        units = await self.validate_tracking(line, item, outward=True)
        position, balance = await self.position(line, warehouse)
        pool = await self.pool(item, line.warehouse_id)
        if line.quantity > balance.quantity:
            raise ConflictError("insufficient selected position stock; negative stock is blocked")
        states = await self.unit_positions(units)
        unit_origins = {}
        for unit in units:
            state = states.get(unit.id)
            if state is None or state.position_id != position.id or state.origin_id is None:
                raise ConflictError(
                    "serial is not available at the selected warehouse, bin and batch"
                )
            unit_origins[unit.id] = state.origin_id
        if units:
            counts = Counter(unit_origins.values())
            selected = tuple(
                Cohort(identity, Decimal(count)) for identity, count in sorted(counts.items())
            )
            if origins is not None and {entry.origin_id: entry.quantity for entry in origins} != {
                entry.origin_id: entry.quantity for entry in selected
            }:
                raise ConflictError("selected serials differ from the required source origins")
            origins = selected
        elif origins is None:
            origins = await self.available_origins(position.id, line.quantity)
        if source_movement_id is None and transit_source_id is None and not count_adjustment:
            available = await candidates(
                self.db,
                company=self.posting.company_id,
                item=item,
                warehouse=line.warehouse_id,
                day=self.posting.stock_date,
            )
            require_order(
                available,
                {(position.id, entry.origin_id): entry.quantity for entry in origins},
                line.quantity,
                item.issue_strategy,
            )
        if transit_source_id and warehouse.kind != "INTERNAL_TRANSIT":
            raise ConflictError("shipment cost selection belongs only to reserved transit custody")
        costs = await self.cost_out(
            pool,
            line.quantity,
            source_movement_id=transit_source_id,
            assigned_value=transit_value,
        )
        value = sum((entry.value for entry in costs), ZERO)
        movement = self.add(
            StockMovement,
            posting_id=self.posting.id,
            position_id=position.id,
            pool_id=pool.id,
            line_id=line.line_id,
            leg="OUT",
            quantity=-line.quantity,
            source_movement_id=source_movement_id,
        )
        await self.db.flush()
        await self.origin_change(movement, origins, inward=False)
        for allocation in costs:
            layer_id = allocation.identity if pool.method == "FIFO" else None
            self.add(
                StockCostAllocation,
                pool_id=pool.id,
                movement_id=movement.id,
                layer_id=layer_id,
                layer_key=layer_id or EMPTY,
                quantity=allocation.quantity,
                value=allocation.value,
            )
        if transit_units is not None:
            if (
                not transit_source_id
                or {unit.unit_id for unit in transit_units} != set(line.unit_ids)
                or sum((unit.carrying_value for unit in transit_units), ZERO) != value
                or any(unit_origins[unit.unit_id] != unit.origin_id for unit in transit_units)
            ):
                raise ConflictError("transit serial cost differs from its original shipment")
            unit_values = transit_units
        else:
            unit_values = self.split_units(units, unit_origins, costs)
        await self.write_units(movement, unit_values, states, inward=False)
        entry = await self.record_value(movement, pool, balance, -value)
        return Leg(
            movement.id,
            entry.id,
            position.id,
            pool.id,
            -line.quantity,
            -value,
            origins,
            unit_values,
            costs,
        )

    async def transfer(
        self,
        line: StockLine,
        item: StockItemFact,
        source: StockWarehouseFact,
        destination: StockWarehouseFact,
    ) -> tuple[Leg, Leg]:
        if line.destination_warehouse_id != destination.warehouse_id:
            raise ConflictError("transfer destination differs from native warehouse evidence")
        issued = await self.issue(line, item, source)
        destination_line = line.model_copy(
            update={
                "warehouse_id": destination.warehouse_id,
                "bin_id": line.destination_bin_id,
                "destination_warehouse_id": None,
                "destination_bin_id": None,
            }
        )
        received = await self.receive(
            destination_line,
            item,
            destination,
            value=-issued.value,
            origins=issued.origins,
            unit_values=issued.units,
            source_movement_id=issued.movement_id,
            restore_costs=issued.costs if source.warehouse_id == destination.warehouse_id else None,
        )
        if issued.value + received.value or issued.quantity + received.quantity:
            raise ConflictError(
                "warehouse transfer does not conserve company stock quantity and value"
            )
        return issued, received
