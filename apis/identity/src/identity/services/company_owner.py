"""Fixed company-creator bootstrap, never a general self-assignment endpoint."""

from __future__ import annotations

import uuid

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.domain.system_roles import get as system_role
from identity.models import Company, Role, RoleAssignment, RolePermission
from identity.services.audit import record


async def grant_company_creator(
    db: AsyncSession,
    current: Actor,
    company_id: uuid.UUID,
    *,
    reason: str = "company creator bootstrap",
) -> RoleAssignment:
    """Grant fixed company administration and stock-operation roles to its creator.

    The creation route calls this in its transaction. Approved legacy repairs use
    the same ownership checks. Existing revoked/expired grants are never restored.
    Ordinary role assignment and its self/held-permission guards are unchanged.
    """
    current.require_scope("company.create", target=ScopePath())
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if (
        company is None
        or company.tenant_id != current.tenant_id
        or company.created_by != current.user_id
        or company.status != "active"
    ):
        raise PermissionDeniedError("company creator access is unavailable")
    now = utcnow()
    prepared: list[tuple[Role, RoleAssignment | None]] = []
    # Validate the complete fixed role set and every existing assignment before
    # creating either grant. This also preserves explicit legacy revocations.
    for key in ("company_admin", "stock_operator"):
        role = await db.scalar(
            select(Role).where(
                Role.tenant_id == SCOPE_ALL, Role.key == key, Role.is_active.is_(True)
            )
        )
        if role is None:
            raise ConflictError("seed active system roles before creating a company")
        permissions = frozenset(
            await db.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
            )
        )
        if permissions != system_role(key).permissions:
            raise ConflictError("synchronize system role permissions before creating a company")
        existing = await db.scalar(
            select(RoleAssignment).where(
                RoleAssignment.subject_type == "user",
                RoleAssignment.subject_id == current.user_id,
                RoleAssignment.role_id == role.id,
                RoleAssignment.scope_type == "company",
                RoleAssignment.scope_id == company.id,
            )
        )
        if existing is not None and (
            not existing.is_active
            or existing.valid_from > now.date()
            or (existing.valid_to is not None and existing.valid_to < now.date())
        ):
            raise ConflictError("review the existing company creator role assignment")
        prepared.append((role, existing))
    assignments = []
    for role, existing in prepared:
        if existing is not None:
            assignments.append(existing)
            continue
        assignment = RoleAssignment(
            id=uuid7(),
            tenant_id=current.tenant_id,
            subject_type="user",
            subject_id=current.user_id,
            role_id=role.id,
            scope_type="company",
            scope_id=company.id,
            is_active=True,
            valid_from=now.date(),
            valid_to=None,
            granted_by=current.user_id,
            grant_reason=reason,
            created_by=current.user_id,
            updated_by=current.user_id,
        )
        db.add(assignment)
        record(
            db,
            current,
            action="role_assignment.granted",
            entity="role_assignment",
            entity_id=assignment.id,
            company_id=company.id,
            reason=reason,
            changes={
                "role_id": {"from": None, "to": str(role.id)},
                "subject_id": {"from": None, "to": str(current.user_id)},
            },
        )
        assignments.append(assignment)
    await db.flush()
    return assignments[0]
