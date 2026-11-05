"""Handling identity stays stable once a revision references it."""

from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ClassificationMaster
from catalog.models.handling import HandlingProfile, HandlingProfileRevision


async def validate_master(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    if isinstance(row, HandlingProfile) and before and row.code != before["code"]:
        used_handling = await db.scalar(
            select(HandlingProfileRevision.id)
            .where(
                HandlingProfileRevision.company_id == row.company_id,
                HandlingProfileRevision.profile_id == row.id,
            )
            .limit(1)
        )
        if used_handling is not None:
            raise ConflictError("referenced handling policy identity is immutable")
