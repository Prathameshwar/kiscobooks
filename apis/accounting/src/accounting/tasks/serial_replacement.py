"""Retire only never-received identities while the native unit lock is held."""

import uuid

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.stock import StockMovementUnit, StockUnitPosition
from accounting.models.stock_tracking import StockTrackingEvent, StockUnit
from accounting.schemas.stock_tracking import SerialPrepare
from accounting.stock_resources import SERIAL
from accounting.tasks.access import writable


async def retire_unused(db: AsyncSession, access: Access, body: SerialPrepare) -> StockUnit:
    company = access.context.company_id
    assert body.replaces_unit_id is not None
    row = await company_object(db, StockUnit, body.replaces_unit_id, company_id=company, lock=True)
    if row.row_version != body.expected_replaced_version:
        raise ConflictError("original serial has changed; reload before replacing it")
    if row.status != "ACTIVE" or row.is_held:
        raise ConflictError("only an active, unheld serial can be replaced")
    if row.item_id != body.item_id or row.lot_id != body.lot_id:
        raise ConflictError("replacement must retain the original SKU and batch")
    if row.row_version >= 2**31 - 1:
        raise ConflictError("record version is exhausted")
    membership = await db.scalar(
        select(StockMovementUnit.id)
        .where(
            StockMovementUnit.company_id == company,
            StockMovementUnit.unit_id == row.id,
        )
        .limit(1)
    )
    position = await db.scalar(
        select(StockUnitPosition.id)
        .where(
            StockUnitPosition.company_id == company,
            StockUnitPosition.unit_id == row.id,
            StockUnitPosition.position_id.is_not(None) | StockUnitPosition.origin_id.is_not(None),
        )
        .limit(1)
    )
    if membership or position:
        raise ConflictError("received serial identities require a controlled stock correction")
    before = {key: getattr(row, key) for key in SERIAL.detail.model_fields if hasattr(row, key)}
    writable(access, SERIAL, before, before | {"status": "RETIRED"})
    row.status = "RETIRED"
    row.row_version += 1
    row.updated_at, row.updated_by = utcnow(), access.actor.user_id
    return row


async def assert_not_replaced(db: AsyncSession, access: Access, unit_id: uuid.UUID) -> None:
    replaced = await db.scalar(
        select(StockTrackingEvent.id)
        .where(
            StockTrackingEvent.company_id == access.context.company_id,
            StockTrackingEvent.target_id == unit_id,
            StockTrackingEvent.resource == "SERIAL",
            StockTrackingEvent.action == "RETIRE",
            StockTrackingEvent.evidence["id"]["from"].as_string() == str(unit_id),
        )
        .limit(1)
    )
    if replaced:
        raise ConflictError("a replaced serial identity remains retired; use its replacement")
