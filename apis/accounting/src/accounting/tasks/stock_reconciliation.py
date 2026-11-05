"""Owner reconciliation against immutable history, never replacement balance writes.

Call under AccountingSetup's company lock. These probes return one safe failure,
not denied stock/financial figures. They include empty projections and transit;
historical bin value deltas are deliberately not treated as separate assets.
"""

import datetime as dt
import uuid

from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account
from accounting.models.stock import (
    StockAccountPolicy,
    StockBalance,
    StockCostLayer,
    StockCostPool,
    StockExecutionPlan,
    StockMovement,
    StockMovementUnit,
    StockOriginBalance,
    StockPosition,
    StockPosting,
    StockUnitPosition,
    StockValueEntry,
)
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.stock_claim_reconciliation import assert_claims
from accounting.tasks.stock_projection_history import layer_remaining, origin_remaining
from accounting.tasks.stock_totals import total
from accounting.tasks.stock_unit_reconciliation import assert_units


async def assert_physical(db: AsyncSession, company: uuid.UUID) -> None:
    """Reconstruct quantity/value expectations from retained immutable evidence."""
    movement_quantity = (
        select(total(StockMovement.quantity))
        .where(StockMovement.company_id == company, StockMovement.position_id == StockPosition.id)
        .correlate(StockPosition)
        .scalar_subquery()
    )
    origin_quantity = (
        select(total(StockOriginBalance.quantity))
        .where(
            StockOriginBalance.company_id == company,
            StockOriginBalance.position_id == StockPosition.id,
        )
        .correlate(StockPosition)
        .scalar_subquery()
    )
    invalid_position = await db.scalar(
        select(StockPosition.id)
        .outerjoin(StockBalance, StockBalance.position_id == StockPosition.id)
        .where(
            StockPosition.company_id == company,
            or_(
                StockBalance.id.is_(None),
                StockBalance.quantity != movement_quantity,
                StockBalance.quantity != origin_quantity,
            ),
        )
        .limit(1)
    )
    if invalid_position:
        raise ConflictError("stock position quantities do not reconcile to immutable history")

    invalid_origin = await db.scalar(
        select(StockOriginBalance.id)
        .where(
            StockOriginBalance.company_id == company,
            StockOriginBalance.quantity != origin_remaining(company),
        )
        .limit(1)
    )
    if invalid_origin:
        raise ConflictError("stock receipt origins do not reconcile to immutable history")

    pool_quantity = (
        select(total(StockMovement.quantity))
        .where(StockMovement.company_id == company, StockMovement.pool_id == StockCostPool.id)
        .correlate(StockCostPool)
        .scalar_subquery()
    )
    pool_value = (
        select(total(StockValueEntry.amount))
        .where(StockValueEntry.company_id == company, StockValueEntry.pool_id == StockCostPool.id)
        .correlate(StockCostPool)
        .scalar_subquery()
    )
    fifo_quantity = (
        select(total(StockCostLayer.remaining_quantity))
        .where(StockCostLayer.company_id == company, StockCostLayer.pool_id == StockCostPool.id)
        .correlate(StockCostPool)
        .scalar_subquery()
    )
    fifo_value = (
        select(total(StockCostLayer.remaining_value))
        .where(StockCostLayer.company_id == company, StockCostLayer.pool_id == StockCostPool.id)
        .correlate(StockCostPool)
        .scalar_subquery()
    )
    invalid_pool = await db.scalar(
        select(StockCostPool.id)
        .where(
            StockCostPool.company_id == company,
            or_(
                StockCostPool.quantity != pool_quantity,
                StockCostPool.value != pool_value,
                (StockCostPool.method == "FIFO")
                & ((StockCostPool.quantity != fifo_quantity) | (StockCostPool.value != fifo_value)),
            ),
        )
        .limit(1)
    )
    if invalid_pool:
        raise ConflictError("warehouse quantities and costs do not reconcile to immutable history")
    invalid_layer = await db.scalar(
        select(StockCostLayer.id)
        .where(
            StockCostLayer.company_id == company,
            or_(
                StockCostLayer.remaining_quantity != layer_remaining(company),
                StockCostLayer.remaining_value != layer_remaining(company, value=True),
            ),
        )
        .limit(1)
    )
    if invalid_layer:
        raise ConflictError("FIFO residual layers do not reconcile to immutable allocations")

    original_units = (
        select(StockMovementUnit.id)
        .join(StockMovement, StockMovement.id == StockMovementUnit.movement_id)
        .where(
            StockMovementUnit.company_id == company,
            StockMovement.company_id == company,
            StockMovement.position_id == StockPosition.id,
        )
        .correlate(StockPosition)
        .exists()
    )
    units_on_hand = (
        select(func.count(StockUnitPosition.id))
        .where(
            StockUnitPosition.company_id == company,
            StockUnitPosition.position_id == StockPosition.id,
        )
        .correlate(StockPosition)
        .scalar_subquery()
    )
    invalid_units = await db.scalar(
        select(StockPosition.id)
        .join(StockBalance, StockBalance.position_id == StockPosition.id)
        .where(
            StockPosition.company_id == company,
            original_units,
            StockBalance.quantity != units_on_hand,
        )
        .limit(1)
    )
    if invalid_units:
        raise ConflictError("serial custody does not reconcile to physical stock quantities")
    await assert_units(db, company)
    await assert_claims(db, company)


async def assert_value_control(db: AsyncSession, company: uuid.UUID) -> None:
    """All governed inventory accounts, including linked openings, match stock value."""
    stock_value = (
        select(total(StockValueEntry.amount))
        .join(StockMovement, StockMovement.id == StockValueEntry.movement_id)
        .join(StockPosting, StockPosting.id == StockMovement.posting_id)
        .join(StockAccountPolicy, StockAccountPolicy.id == StockPosting.account_policy_id)
        .where(
            StockValueEntry.company_id == company,
            StockMovement.company_id == company,
            StockPosting.company_id == company,
            StockAccountPolicy.company_id == company,
            StockAccountPolicy.inventory_account_id == Account.id,
        )
        .correlate(Account)
        .scalar_subquery()
    )
    accounts = select(StockAccountPolicy.inventory_account_id).where(
        StockAccountPolicy.company_id == company
    )
    signed = case(
        (JournalLine.side == "DEBIT", JournalLine.base_amount), else_=-JournalLine.base_amount
    )
    ledger_value = (
        select(total(signed))
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            JournalLine.company_id == company,
            Journal.company_id == company,
            Journal.status == "POSTED",
            JournalLine.account_id == Account.id,
        )
        .correlate(Account)
        .scalar_subquery()
    )
    invalid = await db.scalar(
        select(Account.id)
        .where(Account.company_id == company, Account.id.in_(accounts), stock_value != ledger_value)
        .limit(1)
    )
    if invalid:
        raise ConflictError("inventory GL accounts do not reconcile to native stock value")


async def closing_checks(
    db: AsyncSession, company: uuid.UUID, start: dt.date, end: dt.date
) -> None:
    pending = await db.scalar(
        select(VoucherMoneyIntent.id)
        .join(StockExecutionPlan, StockExecutionPlan.intent_id == VoucherMoneyIntent.id)
        .where(
            VoucherMoneyIntent.company_id == company,
            StockExecutionPlan.company_id == company,
            VoucherMoneyIntent.posting_date.between(start, end),
            VoucherMoneyIntent.status == "PREPARED",
        )
        .limit(1)
    )
    if pending:
        raise ConflictError("reconcile pending stock executions before closing the period")
    stock_intents = select(StockPosting.intent_id).where(
        StockPosting.company_id == company, StockPosting.posting_date.between(start, end)
    )
    stock_journals = select(StockPosting.journal_id).where(
        StockPosting.company_id == company, StockPosting.posting_date.between(start, end)
    )
    undelivered = await db.scalar(
        select(Outbox.id)
        .where(
            or_(Outbox.aggregate_id.in_(stock_intents), Outbox.aggregate_id.in_(stock_journals)),
            Outbox.event_type == "accounting.stock_posting.confirm",
            Outbox.published_at.is_(None),
        )
        .limit(1)
    )
    if undelivered:
        raise ConflictError("stock posting confirmations must be delivered before closing")
    await assert_physical(db, company)
    await assert_value_control(db, company)
