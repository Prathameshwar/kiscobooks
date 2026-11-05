"""Stable BOM identity after authoring begins."""

from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.boms import Bom, BomDraft
from catalog.models.classification import ClassificationMaster


async def validate_master(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    if isinstance(row, Bom) and before and row.code != before["code"]:
        used = await db.scalar(
            select(BomDraft.id)
            .where(
                BomDraft.company_id == row.company_id,
                BomDraft.bom_id == row.id,
            )
            .limit(1)
        )
        if used is not None:
            raise ConflictError("BOM code is immutable after authoring begins")
