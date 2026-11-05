"""Bounded published SKU unit history for the signed Vouchers owner feed."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item


async def unit_revision_facts(
    db: AsyncSession,
    company_id: uuid.UUID,
    after: uuid.UUID | None,
    limit: int,
) -> tuple[list[dict[str, Any]], uuid.UUID | None]:
    statement = (
        select(ItemUnitRevision, ItemUnitBinding)
        .join(ItemUnitBinding, ItemUnitBinding.id == ItemUnitRevision.binding_id)
        .join(Item, Item.id == ItemUnitBinding.item_id)
        .where(
            ItemUnitRevision.company_id == company_id,
            ItemUnitBinding.company_id == company_id,
            Item.company_id == company_id,
            Item.status == "ACTIVE",
        )
    )
    if after is not None:
        statement = statement.where(ItemUnitRevision.id > after)
    rows = list(await db.execute(statement.order_by(ItemUnitRevision.id).limit(limit + 1)))
    selected = rows[:limit]
    masters = [
        {
            "entity_type": "item_unit_revision",
            "source_id": str(revision.id),
            "source_version": revision.row_version,
            "status": "ACTIVE",
            "facts": {
                "version": 1,
                "item_id": str(binding.item_id),
                "binding_id": str(binding.id),
                "unit_id": str(binding.unit_id),
                "usage_role": binding.usage_role,
                "conversion_mode": revision.conversion_mode,
                "numerator": str(revision.numerator) if revision.numerator is not None else None,
                "denominator": str(revision.denominator)
                if revision.denominator is not None
                else None,
                "quantity_decimal_places": revision.quantity_decimal_places,
                "quantity_increment": str(revision.quantity_increment),
                "fractional_entry": revision.fractional_entry,
                "valid_from": revision.valid_from.isoformat(),
                "valid_to": revision.valid_to.isoformat() if revision.valid_to else None,
            },
        }
        for revision, binding in selected
    ]
    return masters, selected[-1][0].id if len(rows) > limit else None
