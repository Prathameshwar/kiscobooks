"""Reconstruct duplicate-return/transfer claim guards from immutable allocations."""

import uuid
from decimal import Decimal

from billing_platform.errors import ConflictError
from sqlalchemy import SQLColumnExpression, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import ScalarSelect

from accounting.models.stock import (
    StockClaimAllocation,
    StockMovement,
    StockOriginAllocation,
    StockOriginClaim,
    StockPosting,
    StockSourceClaim,
)
from accounting.tasks.stock_totals import total


def cancellation(company: uuid.UUID) -> SQLColumnExpression[bool]:
    cancelled = aliased(StockPosting)
    return (
        select(cancelled.id)
        .where(cancelled.company_id == company, cancelled.reverses_id == StockMovement.posting_id)
        .exists()
    )


def source_history(
    company: uuid.UUID, column: SQLColumnExpression[Decimal]
) -> ScalarSelect[Decimal]:
    # Reversals retain positive historical allocations and unwind their counters.
    return (
        select(total(case((cancellation(company), 0), else_=column)))
        .join(StockMovement, StockMovement.id == StockClaimAllocation.movement_id)
        .where(
            StockClaimAllocation.company_id == company,
            StockMovement.company_id == company,
            StockClaimAllocation.source_movement_id == StockSourceClaim.movement_id,
            StockClaimAllocation.claim_type == StockSourceClaim.claim_type,
        )
        .correlate(StockSourceClaim)
        .scalar_subquery()
    )


def origin_history(company: uuid.UUID) -> ScalarSelect[Decimal]:
    return (
        select(
            total(case((cancellation(company), 0), else_=func.abs(StockOriginAllocation.quantity)))
        )
        .select_from(StockClaimAllocation)
        .join(StockMovement, StockMovement.id == StockClaimAllocation.movement_id)
        .join(StockOriginAllocation, StockOriginAllocation.movement_id == StockMovement.id)
        .where(
            StockClaimAllocation.company_id == company,
            StockMovement.company_id == company,
            StockOriginAllocation.company_id == company,
            StockClaimAllocation.source_movement_id == StockOriginClaim.source_movement_id,
            StockClaimAllocation.claim_type == StockOriginClaim.claim_type,
            StockOriginAllocation.origin_id == StockOriginClaim.origin_id,
        )
        .correlate(StockOriginClaim)
        .scalar_subquery()
    )


async def assert_claims(db: AsyncSession, company: uuid.UUID) -> None:
    invalid = await db.scalar(
        select(StockSourceClaim.id)
        .where(
            StockSourceClaim.company_id == company,
            or_(
                StockSourceClaim.quantity != source_history(company, StockClaimAllocation.quantity),
                StockSourceClaim.value != source_history(company, StockClaimAllocation.value),
            ),
        )
        .limit(1)
    )
    missing = await db.scalar(
        select(StockClaimAllocation.id)
        .outerjoin(
            StockSourceClaim,
            (StockSourceClaim.company_id == company)
            & (StockSourceClaim.movement_id == StockClaimAllocation.source_movement_id)
            & (StockSourceClaim.claim_type == StockClaimAllocation.claim_type),
        )
        .where(StockClaimAllocation.company_id == company, StockSourceClaim.id.is_(None))
        .limit(1)
    )
    invalid_origin = await db.scalar(
        select(StockOriginClaim.id)
        .where(
            StockOriginClaim.company_id == company,
            StockOriginClaim.quantity != origin_history(company),
        )
        .limit(1)
    )
    missing_origin = await db.scalar(
        select(StockClaimAllocation.id)
        .join(
            StockOriginAllocation,
            StockOriginAllocation.movement_id == StockClaimAllocation.movement_id,
        )
        .outerjoin(
            StockOriginClaim,
            (StockOriginClaim.company_id == company)
            & (StockOriginClaim.source_movement_id == StockClaimAllocation.source_movement_id)
            & (StockOriginClaim.claim_type == StockClaimAllocation.claim_type)
            & (StockOriginClaim.origin_id == StockOriginAllocation.origin_id),
        )
        .where(
            StockClaimAllocation.company_id == company,
            StockOriginAllocation.company_id == company,
            StockOriginClaim.id.is_(None),
        )
        .limit(1)
    )
    if invalid or missing or invalid_origin or missing_origin:
        raise ConflictError("stock source claims do not reconcile to immutable allocations")
