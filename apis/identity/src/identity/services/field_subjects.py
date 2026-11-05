"""Bounded active subjects used by Identity's delegated field-policy contexts."""

import uuid

from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import Role, RoleAssignment, UserGroup, UserGroupMember


async def policy_subjects(
    db: AsyncSession, current: Actor
) -> tuple[set[uuid.UUID], list[RoleAssignment]]:
    groups = set(
        await db.scalars(
            select(UserGroupMember.user_group_id)
            .where(UserGroupMember.user_id == current.user_id)
            .limit(1001)
        )
    )
    if len(groups) > 1000:
        raise ValidationFailedError("group membership exceeds the context bound")
    groups = set(
        await db.scalars(
            select(UserGroup.id).where(UserGroup.id.in_(groups), UserGroup.is_active.is_(True))
        )
    )
    today = utcnow().date()
    assignments = list(
        await db.scalars(
            select(RoleAssignment)
            .join(Role)
            .where(
                Role.is_active.is_(True),
                RoleAssignment.is_active.is_(True),
                RoleAssignment.valid_from <= today,
                or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to >= today),
                or_(
                    and_(
                        RoleAssignment.subject_type == "user",
                        RoleAssignment.subject_id == current.user_id,
                    ),
                    and_(
                        RoleAssignment.subject_type == "user_group",
                        RoleAssignment.subject_id.in_(groups),
                    ),
                ),
            )
            .limit(1001)
        )
    )
    if len(assignments) > 1000:
        raise ValidationFailedError("role assignments exceed the context bound")
    return groups, assignments
