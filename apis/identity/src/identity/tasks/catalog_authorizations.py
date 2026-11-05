"""Resolve current native grants for one bounded Catalog job chunk."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.actor_authorization import (
    MAX_LEASE_SECONDS,
    ActorAuthorizationProof,
    ActorAuthorizationRequest,
)
from billing_platform.authz import Grant, Scope, ScopePath, resolve_permissions
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, PlatformError, ValidationFailedError
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import (
    Company,
    Role,
    RoleAssignment,
    RolePermission,
    User,
    UserGroup,
    UserGroupMember,
)
from identity.models.catalog_source import CatalogSourceGeneration

MAX_SUBJECTS = 1000
MAX_ASSIGNMENTS = 1000
REQUESTABLE_PERMISSIONS = CATALOG_PERMISSIONS | {"custom_field.manage"}


class AuthorizationUnavailableError(PlatformError):
    status_code = 503
    code = "authorization_unavailable"


async def authorize_actor(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    request: ActorAuthorizationRequest,
    requestable_permissions: frozenset[str] = REQUESTABLE_PERMISSIONS,
    retained_reports: bool = False,
) -> ActorAuthorizationProof:
    tenant = require_current_tenant()
    if not request.permissions <= requestable_permissions:
        raise ValidationFailedError("requested permission is outside the service contract")
    # Lock before all native reads. This read must NOT increment the source stream:
    # every proof would otherwise invalidate the Catalog checkpoint it must match.
    version = await db.scalar(
        select(CatalogSourceGeneration.version)
        .where(CatalogSourceGeneration.tenant_id == tenant)
        .with_for_update(read=True)
    )
    if version is None:
        raise AuthorizationUnavailableError("verified source bootstrap is required")
    company = await db.scalar(
        select(Company.id).where(
            Company.id == company_id,
            Company.status.in_(("active", "closed"))
            if retained_reports
            else Company.status == "active",
        )
    )
    user = await db.scalar(
        select(User.id).where(User.id == request.user_id, User.status == "active")
    )
    if company is None or user is None:
        raise PermissionDeniedError("actor or company is unavailable for Catalog work")
    groups = list(
        await db.scalars(
            select(UserGroup.id)
            .join(UserGroupMember, UserGroupMember.user_group_id == UserGroup.id)
            .where(UserGroupMember.user_id == request.user_id, UserGroup.is_active.is_(True))
            .limit(MAX_SUBJECTS + 1)
        )
    )
    if len(groups) > MAX_SUBJECTS:
        raise AuthorizationUnavailableError("actor membership exceeds the resolution bound")
    assignments = list(
        await db.scalars(
            select(RoleAssignment)
            .where(
                or_(
                    and_(
                        RoleAssignment.subject_type == "user",
                        RoleAssignment.subject_id == request.user_id,
                    ),
                    and_(
                        RoleAssignment.subject_type == "user_group",
                        RoleAssignment.subject_id.in_(groups),
                    ),
                ),
                or_(
                    and_(
                        RoleAssignment.scope_type == "tenant", RoleAssignment.scope_id == SCOPE_ALL
                    ),
                    and_(
                        RoleAssignment.scope_type == "company",
                        RoleAssignment.scope_id == company_id,
                    ),
                ),
                RoleAssignment.is_active.is_(True),
            )
            .limit(MAX_ASSIGNMENTS + 1)
        )
    )
    if len(assignments) > MAX_ASSIGNMENTS:
        raise AuthorizationUnavailableError("actor assignments exceed the resolution bound")
    permissions: dict[uuid.UUID, set[str]] = {}
    if assignments:
        rows = await db.execute(
            select(RolePermission.role_id, RolePermission.permission_key)
            .join(Role, Role.id == RolePermission.role_id)
            .where(
                Role.id.in_({a.role_id for a in assignments}),
                Role.is_active.is_(True),
                RolePermission.permission_key.in_(request.permissions),
            )
            .limit(MAX_ASSIGNMENTS * 32 + 1)
        )
        for role_id, key in rows:
            permissions.setdefault(role_id, set()).add(key)
    now = utcnow()
    allowed = resolve_permissions(
        (
            Grant(
                frozenset(permissions.get(a.role_id, set())),
                Scope(a.scope_type, a.scope_id),
                a.valid_from,
                a.valid_to,
                a.is_active,
            )
            for a in assignments
        ),
        target=ScopePath(company_id=company_id),
        on_date=now.date(),
    )
    boundary = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.UTC)
    return ActorAuthorizationProof(
        request_id=request.request_id,
        tenant_id=tenant,
        company_id=company_id,
        user_id=request.user_id,
        source_version=version,
        generated_at=now,
        expires_at=min(now + dt.timedelta(seconds=MAX_LEASE_SECONDS), boundary),
        permissions=allowed,
    )
