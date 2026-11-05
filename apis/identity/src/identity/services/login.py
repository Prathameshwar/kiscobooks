"""Resolve verified provider subjects and live local grants with bounded work."""

from __future__ import annotations

import uuid

from billing_platform.authz import Grant, Scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError
from billing_platform.oidc import VerifiedClaims
from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Role, RoleAssignment, RolePermission, User, UserGroup, UserGroupMember

MAX_GROUPS = 256
MAX_GRANTS = 256


async def locate_subject(db: AsyncSession, claims: VerifiedClaims) -> uuid.UUID:
    # The subject is cryptographically verified and globally unique. This lookup
    # returns only the isolation boundary; all profile/authority reads are tenant-filtered.
    with unfiltered():
        tenant_id = await db.scalar(select(User.tenant_id).where(User.authentik_sub == claims.sub))
    if tenant_id is None or (claims.org_id is not None and tenant_id != claims.org_id):
        raise AuthenticationRequiredError("identity is not activated for this tenant")
    return tenant_id


async def live_grants(
    db: AsyncSession, user_id: uuid.UUID, *, include_future: bool = False
) -> tuple[tuple[Grant, ...], frozenset[uuid.UUID]]:
    """The user's grants in force today. ``include_future`` also returns ones that start later.

    Authorization never wants the future ones. A caller deciding whether handing someone a way into
    an account is safe does: a role that starts tomorrow is authority the account already has.
    """
    today = utcnow().date()
    groups = frozenset(
        await db.scalars(
            select(UserGroup.id)
            .join(UserGroupMember, UserGroupMember.user_group_id == UserGroup.id)
            .where(UserGroupMember.user_id == user_id, UserGroup.is_active.is_(True))
            .limit(MAX_GROUPS + 1)
        )
    )
    if len(groups) > MAX_GROUPS:
        raise AuthenticationRequiredError("identity exceeds the authority resolution bound")
    assignments = list(
        await db.scalars(
            select(RoleAssignment)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.is_active.is_(True),
                Role.is_active.is_(True),
                true() if include_future else RoleAssignment.valid_from <= today,
                or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to >= today),
                or_(
                    and_(
                        RoleAssignment.subject_type == "user", RoleAssignment.subject_id == user_id
                    ),
                    and_(
                        RoleAssignment.subject_type == "user_group",
                        RoleAssignment.subject_id.in_(groups),
                    ),
                ),
            )
            .limit(MAX_GRANTS + 1)
        )
    )
    if len(assignments) > MAX_GRANTS:
        raise AuthenticationRequiredError("identity exceeds the authority resolution bound")
    permissions: dict[uuid.UUID, set[str]] = {}
    if assignments:
        for role_id, permission in await db.execute(
            select(RolePermission.role_id, RolePermission.permission_key).where(
                RolePermission.role_id.in_({a.role_id for a in assignments})
            )
        ):
            permissions.setdefault(role_id, set()).add(permission)
    return tuple(
        Grant(
            frozenset(permissions.get(a.role_id, ())),
            Scope(a.scope_type, a.scope_id),
            a.valid_from,
            a.valid_to,
            True,
        )
        for a in assignments
    ), groups
