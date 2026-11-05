"""Retained physical evidence prevents reinterpretation through later owner definitions."""

import uuid

from billing_platform.errors import ConflictError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock_facts import StockFenceFacts

from accounting.models.stock import StockMovement, StockPosition, StockPosting

IDENTITY_FIELDS = (
    "base_unit_id",
    "quantity_increment",
    "quantity_decimal_places",
    "profile_id",
    "profile_revision_id",
    "lot_tracking",
    "serial_tracking",
    "expiry_required",
    "manufacture_date_required",
    "valuation_method",
)


async def assert_retained(db: AsyncSession, company: uuid.UUID, facts: StockFenceFacts) -> None:
    """Caller holds AccountingSetup; a new warehouse cannot evade this company/item ratchet.

    This baseline has no tracking/base-unit/cost-method migration. New gateway
    authority or a newer Catalog row version never authorizes rewriting old goods.
    Nonstructural sale/purchase/location controls still resolve from current facts.
    """
    for item in facts.items:
        evidence = await db.scalar(
            select(StockPosting.source_facts)
            .join(StockMovement, StockMovement.posting_id == StockPosting.id)
            .join(StockPosition, StockPosition.id == StockMovement.position_id)
            .where(
                StockPosting.company_id == company,
                StockMovement.company_id == company,
                StockPosition.company_id == company,
                StockPosition.item_id == item.item_id,
            )
            .order_by(StockPosting.id)
            .limit(1)
        )
        if evidence is None:
            continue
        try:
            original = StockFenceFacts.model_validate(evidence.get("catalog"))
        except ValidationError as exc:
            raise ConflictError(
                "retained stock definition requires controlled reconciliation"
            ) from exc
        previous = next((row for row in original.items if row.item_id == item.item_id), None)
        if previous is None or any(
            getattr(previous, key) != getattr(item, key) for key in IDENTITY_FIELDS
        ):
            raise ConflictError(
                "current product rules differ from its retained stock definition; "
                "restore the original rules or complete a reviewed stock migration"
            )
