"""Exact serial custody reconstruction; matching counts alone cannot verify identities."""

import uuid

from billing_platform.errors import ConflictError
from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import Subquery

from accounting.models.stock import (
    StockMovement,
    StockMovementUnit,
    StockPosting,
    StockUnitPosition,
)
from accounting.tasks.stock_ordering import assert_committed, generation


def unit_history(company: uuid.UUID) -> Subquery:
    later = aliased(StockMovementUnit)
    later_movement = aliased(StockMovement)
    later_posting = aliased(StockPosting)
    original = aliased(StockMovement)
    original_posting = aliased(StockPosting)
    latest = (
        ~select(later.id)
        .join(later_movement, later_movement.id == later.movement_id)
        .join(later_posting, later_posting.id == later_movement.posting_id)
        .where(
            later.company_id == company,
            later.unit_id == StockMovementUnit.unit_id,
            or_(
                generation(later_posting) > generation(StockPosting),
                and_(
                    later_posting.id == StockPosting.id,
                    later.id > StockMovementUnit.id,
                ),
                and_(
                    generation(later_posting).is_(None),
                    generation(StockPosting).is_(None),
                    later.id > StockMovementUnit.id,
                ),
            ),
        )
        .correlate(StockMovementUnit, StockPosting)
        .exists()
    )
    # Reversing an initial receipt restores preparation, including its empty origin.
    restored_preparation = (
        (StockPosting.action == "REVERSAL")
        & (StockMovement.leg == "OUT")
        & original_posting.action.in_(("RECEIPT", "OPENING"))
    )
    origin = case((restored_preparation, None), else_=StockMovementUnit.origin_id)
    position = case((StockMovement.leg == "IN", StockMovement.position_id), else_=None)
    return (
        select(
            StockMovementUnit.unit_id.label("unit_id"),
            StockMovement.id.label("movement_id"),
            position.label("position_id"),
            origin.label("origin_id"),
        )
        .join(StockMovement, StockMovement.id == StockMovementUnit.movement_id)
        .join(StockPosting, StockPosting.id == StockMovement.posting_id)
        .outerjoin(original, original.id == StockMovement.source_movement_id)
        .outerjoin(original_posting, original_posting.id == original.posting_id)
        .where(
            StockMovementUnit.company_id == company,
            StockMovement.company_id == company,
            StockPosting.company_id == company,
            latest,
        )
        .subquery()
    )


async def assert_units(db: AsyncSession, company: uuid.UUID) -> None:
    await assert_committed(db, company)
    history = unit_history(company)
    invalid = (
        await db.execute(
            select(StockUnitPosition.id, history.c.unit_id)
            .select_from(history)
            .outerjoin(
                StockUnitPosition,
                (StockUnitPosition.company_id == company)
                & (StockUnitPosition.unit_id == history.c.unit_id),
            )
            .where(
                or_(
                    StockUnitPosition.id.is_(None),
                    StockUnitPosition.last_movement_id != history.c.movement_id,
                    StockUnitPosition.position_id.is_distinct_from(history.c.position_id),
                    StockUnitPosition.origin_id.is_distinct_from(history.c.origin_id),
                ),
            )
            .limit(1)
        )
    ).first()
    retained = (
        select(StockMovementUnit.id)
        .where(
            StockMovementUnit.company_id == company,
            StockMovementUnit.unit_id == StockUnitPosition.unit_id,
            StockMovementUnit.movement_id == StockUnitPosition.last_movement_id,
        )
        .exists()
    )
    orphan = await db.scalar(
        select(StockUnitPosition.id)
        .where(StockUnitPosition.company_id == company, ~retained)
        .limit(1)
    )
    if invalid or orphan:
        raise ConflictError(
            "serial custody does not reconcile to its immutable movement identities"
        )
