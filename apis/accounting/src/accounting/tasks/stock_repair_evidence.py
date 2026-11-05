"""Reject incomplete native immutable history before proposing projection recovery."""

from collections import Counter

from billing_platform.errors import ConflictError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock import StockInput
from voucher_execution.stock_facts import StockFenceFacts

from accounting.models import stock as s
from accounting.tasks.stock_totals import total


async def assert_history(db: AsyncSession, posting: s.StockPosting) -> None:
    if posting.account_policy_id is None:
        return  # Low-level storage fixtures have no public execution/source protocol.
    message = "immutable stock history is incomplete; reviewed recovery is required"
    try:
        body = StockInput.model_validate(posting.source_facts.get("stock"))
        facts = StockFenceFacts.model_validate(posting.source_facts.get("catalog"))
    except ValidationError as exc:
        raise ConflictError(message) from exc
    if (
        body.currency != posting.currency
        or facts.tenant_id != posting.tenant_id
        or facts.company_id != posting.company_id
        or facts.execution_id != posting.execution_id
        or facts.content_hash != posting.content_hash
        or facts.stock_date != posting.stock_date
    ):
        raise ConflictError(message)
    expected = {line.line_id: line for line in body.lines}
    items = {item.item_id: item for item in facts.items}
    rows = (
        await db.execute(
            select(s.StockMovement, s.StockPosition, s.StockValueEntry, s.StockCostPoolEvent)
            .select_from(s.StockMovement)
            .join(s.StockPosition, s.StockPosition.id == s.StockMovement.position_id)
            .outerjoin(s.StockValueEntry, s.StockValueEntry.movement_id == s.StockMovement.id)
            .outerjoin(s.StockCostPoolEvent, s.StockCostPoolEvent.movement_id == s.StockMovement.id)
            .where(
                s.StockMovement.company_id == posting.company_id,
                s.StockMovement.posting_id == posting.id,
            )
            .limit(201)
        )
    ).all()
    legs = 2 if body.action in {"TRANSFER", "TRANSFER_DISPATCH", "TRANSFER_RECEIPT"} else 1
    if len(rows) != len(expected) * legs:
        raise ConflictError(message)
    counts: Counter[object] = Counter()
    for movement, position, value, event in rows:
        line = expected.get(movement.line_id)
        item = items.get(position.item_id)
        if (
            line is None
            or item is None
            or value is None
            or event is None
            or position.company_id != posting.company_id
            or value.company_id != posting.company_id
            or event.company_id != posting.company_id
            or value.pool_id != movement.pool_id
            or event.pool_id != movement.pool_id
            or value.currency != posting.currency
            or event.currency != posting.currency
            or position.item_id != line.item_id
            or position.lot_id != line.lot_id
            or abs(movement.quantity) != line.quantity
            or event.after_quantity - event.before_quantity != movement.quantity
            or event.after_value - event.before_value != value.amount
        ):
            raise ConflictError(message)
        counts[line.line_id] += 1
        origins = await db.scalar(
            select(total(s.StockOriginAllocation.quantity)).where(
                s.StockOriginAllocation.company_id == posting.company_id,
                s.StockOriginAllocation.movement_id == movement.id,
            )
        )
        if origins != movement.quantity:
            raise ConflictError(message)
        if item.serial_tracking:
            members, carrying = (
                await db.execute(
                    select(
                        func.count(s.StockMovementUnit.id),
                        total(s.StockMovementUnit.carrying_value),
                    ).where(
                        s.StockMovementUnit.company_id == posting.company_id,
                        s.StockMovementUnit.movement_id == movement.id,
                    )
                )
            ).one()
            if members != abs(movement.quantity) or carrying != abs(value.amount):
                raise ConflictError(message)
    if counts != Counter({key: legs for key in expected}):
        raise ConflictError(message)
