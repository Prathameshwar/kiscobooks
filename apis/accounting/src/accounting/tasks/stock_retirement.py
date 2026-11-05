"""Current native NoStock evidence under the physical posting company lock.

A displayed available quantity or an old consumer acknowledgement is insufficient.
This is the Accounting half of coordinated retirement, not a Catalog clearance by
itself. The adapter must also fence current Catalog leases and pending Vouchers.
"""

import uuid
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement
from voucher_execution.retirement_transport import RetirementUnavailableError

from accounting.domain.master_metadata import METADATA_VERSION
from accounting.models.masters import AccountingSetup
from accounting.models.stock import (
    StockBalance,
    StockCostPool,
    StockExecutionPlan,
    StockMovement,
    StockPosition,
    StockSourceClaim,
    StockTransferDestination,
    StockUnitPosition,
)
from accounting.models.voucher_money import VoucherMoneyIntent

Reason = Literal["STOCK_ON_HAND", "OPEN_TRANSFER", "PENDING_DOCUMENT"]


async def no_stock(
    db: AsyncSession,
    company: uuid.UUID,
    warehouse: uuid.UUID,
    *,
    bin_id: uuid.UUID | None = None,
) -> Reason | None:
    """Return a safe reason, or current local clearance; never commits or calls another owner."""
    setup = await db.scalar(
        select(AccountingSetup)
        .where(
            AccountingSetup.company_id == company,
        )
        .with_for_update()
    )
    if setup is None or setup.metadata_version != METADATA_VERSION:
        raise RetirementUnavailableError(
            "current Accounting setup is required to check stock retirement"
        )

    def location(model: type[StockPosition]) -> ColumnElement[bool]:
        terms = [model.company_id == company, model.warehouse_id == warehouse]
        if bin_id is not None:
            terms.append(model.bin_key == bin_id)
        return and_(*terms)

    quantity = await db.scalar(
        select(StockBalance.id)
        .join(
            StockPosition,
            and_(
                StockPosition.company_id == StockBalance.company_id,
                StockPosition.id == StockBalance.position_id,
            ),
        )
        .where(location(StockPosition), StockBalance.quantity != 0)
        .limit(1)
    )
    units = await db.scalar(
        select(StockUnitPosition.id)
        .join(
            StockPosition,
            and_(
                StockPosition.company_id == StockUnitPosition.company_id,
                StockPosition.id == StockUnitPosition.position_id,
            ),
        )
        .where(location(StockPosition))
        .limit(1)
    )
    if quantity is not None or units is not None:
        return "STOCK_ON_HAND"
    if bin_id is None:
        pool = await db.scalar(
            select(StockCostPool.id)
            .where(
                StockCostPool.company_id == company,
                StockCostPool.warehouse_id == warehouse,
                or_(StockCostPool.quantity != 0, StockCostPool.value != 0),
            )
            .limit(1)
        )
        if pool is not None:
            return "STOCK_ON_HAND"
    # Bins share their warehouse cost pool. A historical sum of movement values
    # at a bin is not a residual asset: physical FEFO and financial FIFO/MVA may
    # consume different origins. Zero bin quantity/unit custody carries no share
    # of that warehouse pool; the parent must still clear its whole pool to retire.
    transit, source = aliased(StockMovement), aliased(StockMovement)
    source_position, destination = aliased(StockPosition), aliased(StockPosition)
    received, reversed_claim = aliased(StockSourceClaim), aliased(StockSourceClaim)
    shipment = (
        select(StockTransferDestination.id)
        .join(
            transit,
            and_(
                transit.company_id == StockTransferDestination.company_id,
                transit.id == StockTransferDestination.transit_movement_id,
            ),
        )
        .join(
            source,
            and_(source.company_id == transit.company_id, source.id == transit.source_movement_id),
        )
        .join(
            source_position,
            and_(
                source_position.company_id == source.company_id,
                source_position.id == source.position_id,
            ),
        )
        .join(
            destination,
            and_(
                destination.company_id == StockTransferDestination.company_id,
                destination.id == StockTransferDestination.destination_position_id,
            ),
        )
        .outerjoin(
            received,
            and_(
                received.company_id == transit.company_id,
                received.movement_id == transit.id,
                received.claim_type == "TRANSFER",
            ),
        )
        .outerjoin(
            reversed_claim,
            and_(
                reversed_claim.company_id == transit.company_id,
                reversed_claim.movement_id == transit.id,
                reversed_claim.claim_type == "REVERSAL",
            ),
        )
        .where(
            StockTransferDestination.company_id == company,
            transit.quantity
            > func.coalesce(received.quantity, 0) + func.coalesce(reversed_claim.quantity, 0),
        )
    )
    for endpoint in (source_position, destination):
        if await db.scalar(shipment.where(location(endpoint)).limit(1)) is not None:
            return "OPEN_TRANSFER"
    pending = await db.scalar(
        select(StockExecutionPlan.id)
        .join(
            VoucherMoneyIntent,
            and_(
                VoucherMoneyIntent.company_id == StockExecutionPlan.company_id,
                VoucherMoneyIntent.id == StockExecutionPlan.intent_id,
            ),
        )
        .where(
            StockExecutionPlan.company_id == company,
            VoucherMoneyIntent.status == "PREPARED",
        )
        .limit(1)
    )
    return "PENDING_DOCUMENT" if pending is not None else None
