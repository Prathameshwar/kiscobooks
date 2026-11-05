"""Bounded physical issue order; valuation is deliberately not an input."""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from billing_platform.errors import ConflictError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock_facts import StockItemFact

from accounting.models.stock import (
    StockMovement,
    StockOriginBalance,
    StockPosition,
    StockPosting,
    StockReceiptOrigin,
    StockUnitPosition,
)
from accounting.models.stock_tracking import StockLot, StockUnit
from accounting.tasks.stock_ordering import movement_generation


@dataclass(frozen=True)
class Candidate:
    position_id: uuid.UUID
    origin_id: uuid.UUID
    quantity: Decimal
    lot_id: uuid.UUID | None
    bin_id: uuid.UUID | None
    received_on: dt.date
    expires_on: dt.date | None
    history_known: bool = True


async def candidates(
    db: AsyncSession,
    *,
    company: uuid.UUID,
    item: StockItemFact,
    warehouse: uuid.UUID,
    day: dt.date,
) -> tuple[Candidate, ...]:
    """At most 200 eligible cohorts plus an overflow sentinel, in physical order.

    The caller owns the company Accounting lock before using these facts to post.
    Read-only previews cannot establish a reservation or authorize execution.
    """
    serials = (
        select(func.count(StockUnitPosition.id))
        .join(
            StockUnit,
            and_(
                StockUnit.company_id == StockUnitPosition.company_id,
                StockUnit.id == StockUnitPosition.unit_id,
            ),
        )
        .where(
            StockUnitPosition.company_id == company,
            StockUnitPosition.position_id == StockPosition.id,
            StockUnitPosition.origin_id == StockReceiptOrigin.id,
            StockUnit.status == "ACTIVE",
            StockUnit.is_held.is_(False),
        )
        .correlate(StockPosition, StockReceiptOrigin)
        .scalar_subquery()
    )
    quantity = serials if item.serial_tracking else StockOriginBalance.quantity
    earliest_expiry = day + dt.timedelta(days=item.minimum_remaining_life_days or 0)
    receipt_order = movement_generation(company, StockReceiptOrigin.movement_id)
    query = (
        select(
            StockPosition.id,
            StockReceiptOrigin.id,
            quantity,
            StockPosition.lot_id,
            StockPosition.bin_id,
            StockReceiptOrigin.received_on,
            StockLot.expires_on,
            func.coalesce(StockReceiptOrigin.history_known, StockPosting.action != "OPENING"),
            receipt_order,
        )
        .select_from(StockPosition)
        .join(
            StockOriginBalance,
            and_(
                StockOriginBalance.company_id == StockPosition.company_id,
                StockOriginBalance.position_id == StockPosition.id,
            ),
        )
        .join(
            StockReceiptOrigin,
            and_(
                StockReceiptOrigin.company_id == StockOriginBalance.company_id,
                StockReceiptOrigin.id == StockOriginBalance.origin_id,
            ),
        )
        .outerjoin(
            StockLot,
            and_(
                StockLot.company_id == StockPosition.company_id,
                StockLot.id == StockPosition.lot_id,
            ),
        )
        .join(
            StockMovement,
            and_(
                StockMovement.company_id == company,
                StockMovement.id == StockReceiptOrigin.movement_id,
            ),
        )
        .join(
            StockPosting,
            and_(StockPosting.company_id == company, StockPosting.id == StockMovement.posting_id),
        )
        .where(
            StockPosition.company_id == company,
            StockPosition.item_id == item.item_id,
            StockPosition.warehouse_id == warehouse,
            StockPosition.custody_kind == "WAREHOUSE",
            StockPosition.disposition == "USABLE",
            StockOriginBalance.quantity > 0,
            StockReceiptOrigin.received_on <= day,
            quantity > 0,
            or_(
                StockPosition.lot_id.is_(None),
                and_(
                    StockLot.status == "ACTIVE",
                    StockLot.is_held.is_(False),
                    or_(StockLot.manufactured_on.is_(None), StockLot.manufactured_on <= day),
                    or_(StockLot.expires_on.is_(None), StockLot.expires_on >= earliest_expiry),
                ),
            ),
        )
    )
    if item.lot_tracking:
        query = query.where(StockPosition.lot_id.is_not(None))
    else:
        query = query.where(StockPosition.lot_id.is_(None))
    if item.expiry_required or (item.minimum_remaining_life_days or 0) > 0:
        query = query.where(StockLot.expires_on.is_not(None))
    if item.manufacture_date_required:
        query = query.where(StockLot.manufactured_on.is_not(None))
    if item.issue_strategy == "FEFO":
        query = query.order_by(StockLot.expires_on.is_(None), StockLot.expires_on)
    query = query.order_by(
        StockReceiptOrigin.received_on,
        receipt_order,
        StockReceiptOrigin.id,
        StockPosition.id,
    ).limit(201)
    rows = (await db.execute(query)).all()
    if any(row[-1] is None for row in rows):
        raise ConflictError("physical receipt committed owner order is unavailable")
    return tuple(Candidate(*row[:-1]) for row in rows)


def require_order(
    available: tuple[Candidate, ...],
    selected: dict[tuple[uuid.UUID, uuid.UUID], Decimal],
    quantity: Decimal,
    strategy: str,
) -> None:
    remaining = quantity
    for candidate in available[:200]:
        used = min(candidate.quantity, remaining)
        if selected.get((candidate.position_id, candidate.origin_id), Decimal(0)) != used:
            raise ConflictError(
                f"select the earliest eligible {strategy} stock before later batches or receipts"
            )
        remaining -= used
        if remaining == 0:
            return
    raise ConflictError(
        "eligible stock selection exceeds its bounded cohort window; split the issue"
    )
