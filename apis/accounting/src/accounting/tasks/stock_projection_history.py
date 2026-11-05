"""Shared immutable-history expectations for owner reconciliation and repair."""

import uuid
from decimal import Decimal

from sqlalchemy import SQLColumnExpression, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import ScalarSelect

from accounting.models.stock import StockCostAllocation, StockCostLayer, StockMovement, StockPosting
from accounting.tasks.stock_totals import total


def layer_remaining(
    company: uuid.UUID, *, value: bool = False
) -> SQLColumnExpression[Decimal]:
    column = StockCostAllocation.value if value else StockCostAllocation.quantity
    consumed = (
        select(total(column))
        .where(
            StockCostAllocation.company_id == company,
            StockCostAllocation.layer_id == StockCostLayer.id,
        )
        .correlate(StockCostLayer)
        .scalar_subquery()
    )
    original = aliased(StockMovement)
    created_layer = aliased(StockCostLayer)
    restored = (
        select(total(column))
        .select_from(StockMovement)
        .join(StockPosting, StockPosting.id == StockMovement.posting_id)
        .join(original, original.id == StockMovement.source_movement_id)
        .join(StockCostAllocation, StockCostAllocation.movement_id == original.id)
        .where(
            StockMovement.company_id == company,
            original.company_id == company,
            StockPosting.company_id == company,
            StockCostAllocation.company_id == company,
            StockMovement.leg == "IN",
            original.leg == "OUT",
            StockMovement.pool_id == original.pool_id,
            StockPosting.action.in_(("TRANSFER", "REVERSAL")),
            StockCostAllocation.layer_id == StockCostLayer.id,
            ~select(created_layer.id)
            .where(
                created_layer.company_id == company,
                created_layer.movement_id == StockMovement.id,
            )
            .exists(),
        )
        .correlate(StockCostLayer)
        .scalar_subquery()
    )
    return (StockCostLayer.value if value else StockCostLayer.quantity) - consumed + restored


def origin_remaining(company: uuid.UUID) -> ScalarSelect[Decimal]:
    from accounting.models.stock import StockOriginAllocation, StockOriginBalance

    return (
        select(total(StockOriginAllocation.quantity))
        .join(StockMovement, StockMovement.id == StockOriginAllocation.movement_id)
        .where(
            StockOriginAllocation.company_id == company,
            StockMovement.company_id == company,
            StockOriginAllocation.origin_id == StockOriginBalance.origin_id,
            StockMovement.position_id == StockOriginBalance.position_id,
        )
        .correlate(StockOriginBalance)
        .scalar_subquery()
    )
