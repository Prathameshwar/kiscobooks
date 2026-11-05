"""Return identity stays stable once a revision references it."""

from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from catalog.models.classification import ClassificationMaster
from catalog.models.returns import ReturnPolicy, ReturnPolicyCondition, ReturnPolicyRevision


def incomplete_conditions() -> ColumnElement[bool]:
    actual = (
        select(func.count(ReturnPolicyCondition.id))
        .where(
            ReturnPolicyCondition.tenant_id == ReturnPolicyRevision.tenant_id,
            ReturnPolicyCondition.company_id == ReturnPolicyRevision.company_id,
            ReturnPolicyCondition.revision_id == ReturnPolicyRevision.id,
        )
        .correlate(ReturnPolicyRevision)
        .scalar_subquery()
    )
    return actual != ReturnPolicyRevision.condition_count


async def validate_master(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    if isinstance(row, ReturnPolicy) and before and row.code != before["code"]:
        used_return = await db.scalar(
            select(ReturnPolicyRevision.id)
            .where(
                ReturnPolicyRevision.company_id == row.company_id,
                ReturnPolicyRevision.policy_id == row.id,
            )
            .limit(1)
        )
        if used_return is not None:
            raise ConflictError("referenced return policy identity is immutable")
    if isinstance(row, ReturnPolicy) and row.is_active and before and not before["is_active"]:
        invalid = await db.scalar(
            select(ReturnPolicyRevision.id)
            .where(
                ReturnPolicyRevision.company_id == row.company_id,
                ReturnPolicyRevision.policy_id == row.id,
                ReturnPolicyRevision.published_at.is_not(None),
                incomplete_conditions(),
            )
            .limit(1)
        )
        if invalid is not None:
            raise ConflictError("published return policy conditions are incomplete")
