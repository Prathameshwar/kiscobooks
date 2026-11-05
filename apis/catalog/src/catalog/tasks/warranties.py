"""Warranty identity stays stable once a revision references it."""

from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ClassificationMaster
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision


async def validate_master(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    if isinstance(row, WarrantyPolicy) and before and row.code != before["code"]:
        used_warranty = await db.scalar(
            select(WarrantyPolicyRevision.id)
            .where(
                WarrantyPolicyRevision.company_id == row.company_id,
                WarrantyPolicyRevision.policy_id == row.id,
            )
            .limit(1)
        )
        if used_warranty is not None:
            raise ConflictError("referenced warranty policy identity is immutable")
