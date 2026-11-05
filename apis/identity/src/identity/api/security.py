"""Identity object ancestry and serialized authorization decisions."""

from __future__ import annotations

import uuid
from dataclasses import replace

from billing_platform.authz import Scope, ScopePath, has_permission
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import and_, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from identity.api.auth import Actor
from identity.domain import authorization
from identity.models import (
    Company,
    Department,
    FieldPolicy,
    Role,
    RoleAssignment,
    RolePermission,
    Tenant,
    User,
    UserGroup,
    UserGroupMember,
)
from identity.services.field_delegation import (
    DelegationCache,
    assert_field_delegation,
    registered,
)


async def lock_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    # Administrative mutations lock before policy reads, then company/user rows,
    # then the Catalog generation. This also serializes tree and feature changes.
    if await db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()) is None:
        raise NotFoundError("tenant not found")


def department_target(row: Department) -> ScopePath:
    try:
        ancestors = tuple(uuid.UUID(hex=part) for part in row.path.strip("/").split("/"))
    except ValueError as exc:
        raise ValidationFailedError("department ancestry needs repair") from exc
    if not ancestors or ancestors[-1] != row.id:
        raise ValidationFailedError("department ancestry needs repair")
    return ScopePath(
        company_id=row.company_id, department_id=row.id, department_ancestors=ancestors[:-1]
    )


async def assignment_target(
    db: AsyncSession, scope_type: str, scope_id: uuid.UUID | None
) -> ScopePath:
    if scope_type == "tenant":
        if scope_id not in (None, SCOPE_ALL):
            raise ValidationFailedError("tenant scope does not name an object")
        return ScopePath()
    if scope_id is None or scope_id == SCOPE_ALL:
        raise ValidationFailedError("a scoped assignment must name a real object")
    if scope_type == "company":
        row = await db.get(Company, scope_id)
        if row is None:
            raise ValidationFailedError(
                "unknown company", fields={"scope_id": "not in this tenant"}
            )
        return ScopePath(company_id=row.id)
    if scope_type == "department":
        department = await db.get(Department, scope_id)
        if department is None:
            raise ValidationFailedError(
                "unknown department", fields={"scope_id": "not in this tenant"}
            )
        return department_target(department)
    raise ValidationFailedError("unsupported assignment scope")


async def assignment_actor(db: AsyncSession, current: Actor) -> authorization.Actor:
    groups = frozenset(
        await db.scalars(
            select(UserGroupMember.user_group_id).where(UserGroupMember.user_id == current.user_id)
        )
    )
    return replace(current.as_domain_actor(), group_ids=groups | current.group_ids)


async def guard_role_fields(
    db: AsyncSession,
    current: Actor,
    role_id: uuid.UUID,
    assignment_scope: ScopePath,
    cache: DelegationCache | None = None,
) -> None:
    """Role membership can also introduce or remove field-policy exceptions.

    ``cache`` is the caller's when this runs once per assignment in a loop; one is
    created here otherwise, so even a single call resolves the actor's own authority
    once rather than once per policy on the role.
    """
    cache = cache if cache is not None else DelegationCache()
    policies = cache.role_policies.get(role_id)
    if policies is None:
        policies = list(
            await db.scalars(
                select(FieldPolicy)
                .where(
                    FieldPolicy.subject_type == "role",
                    FieldPolicy.subject_id == role_id,
                    FieldPolicy.is_active.is_(True),
                )
                .limit(1001)
            )
        )
        if len(policies) > 1000:
            raise ValidationFailedError("role policy count exceeds its bound")
        cache.role_policies[role_id] = policies
    for policy in policies:
        if not registered(policy.entity_type):
            continue
        policy_scope = await assignment_target(db, policy.scope_type, policy.scope_id)
        if assignment_scope.includes(Scope(policy.scope_type, policy.scope_id)):
            target = assignment_scope
        elif policy_scope.includes(assignment_scope.scopes()[-1]):
            target = policy_scope
        else:
            continue
        if policy.access not in {"read", "write"}:
            raise PermissionDeniedError("unsupported field access")
        await assert_field_delegation(
            db,
            current,
            entity_type=policy.entity_type,
            field_key=policy.field_key,
            access="read" if policy.access == "read" else "write",
            target=target,
            cache=cache,
        )


async def guard_group_join(
    db: AsyncSession, current: Actor, group_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> None:
    """Check what a group carries before its membership or lifecycle changes.

    ``user_id`` is the person joining. A change to the group itself — a removal, or
    its lifecycle — has no single subject, and the assignment's actual subject is the
    **group**, so that is what the guards are given. Passing a placeholder user
    instead made guard 2's own sentinel check refuse the whole operation.
    """
    assignments = list(
        await db.scalars(
            select(RoleAssignment)
            .where(
                RoleAssignment.subject_type == "user_group",
                RoleAssignment.subject_id == group_id,
                RoleAssignment.is_active.is_(True),
                or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to >= utcnow().date()),
            )
            .limit(1001)
        )
    )
    if len(assignments) > 1000:
        raise ValidationFailedError("group assignment count exceeds its bound")
    policies = list(
        await db.scalars(
            select(FieldPolicy)
            .where(
                FieldPolicy.subject_type == "user_group",
                FieldPolicy.subject_id == group_id,
                FieldPolicy.is_active.is_(True),
            )
            .limit(1001)
        )
    )
    if len(policies) > 1000:
        raise ValidationFailedError("group policy count exceeds its bound")
    if not assignments and not policies:
        return
    if user_id == current.user_id:
        raise PermissionDeniedError("you cannot join a group that grants access to yourself")
    cache = DelegationCache()
    if policies:
        current.require_scope("field_policy.manage", target=ScopePath())
        for policy in policies:
            if not registered(policy.entity_type):
                continue
            if policy.access not in {"read", "write"}:
                raise PermissionDeniedError("unsupported field access")
            await assert_field_delegation(
                db,
                current,
                entity_type=policy.entity_type,
                field_key=policy.field_key,
                access="read" if policy.access == "read" else "write",
                target=await assignment_target(db, policy.scope_type, policy.scope_id),
                cache=cache,
            )
    actor = await assignment_actor(db, current)
    for assignment in assignments:
        role = await db.get(Role, assignment.role_id)
        if role is None or not role.is_active:
            continue
        permissions = frozenset(
            await db.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
            )
        )
        target = await assignment_target(db, assignment.scope_type, assignment.scope_id)
        authorization.assert_assignment_change_allowed(
            authorization.AssignmentChange(
                subject_type="user" if user_id is not None else "user_group",
                subject_id=user_id if user_id is not None else group_id,
                role_permissions=permissions,
                target=target,
            ),
            actor=actor,
            on_date=utcnow().date(),
        )
        await guard_role_fields(db, current, role.id, target, cache)


async def guard_role_change(
    db: AsyncSession, current: Actor, role_id: uuid.UUID, permissions: frozenset[str]
) -> None:
    """Editing a used bundle changes access just as granting or revoking it does."""
    domain_actor = await assignment_actor(db, current)
    cache = DelegationCache()
    assignments = list(
        await db.scalars(
            select(RoleAssignment)
            .where(
                RoleAssignment.role_id == role_id,
                RoleAssignment.is_active.is_(True),
                or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to >= utcnow().date()),
            )
            .limit(1001)
        )
    )
    if len(assignments) > 1000:
        raise ValidationFailedError("role assignment count exceeds its bound")
    for assignment in assignments:
        target = await assignment_target(db, assignment.scope_type, assignment.scope_id)
        authorization.assert_assignment_change_allowed(
            authorization.AssignmentChange(
                assignment.subject_type,
                assignment.subject_id,
                permissions,
                target,
            ),
            actor=domain_actor,
            on_date=utcnow().date(),
        )
        await guard_role_fields(db, current, role_id, target, cache)


async def department_filter(
    db: AsyncSession, current: Actor, permission: str, company_id: uuid.UUID
) -> ColumnElement[bool]:
    target = ScopePath(company_id=company_id)
    if has_permission(current.grants, permission, target=target, on_date=utcnow().date()):
        return true()
    clauses: list[ColumnElement[bool]] = []
    for grant in current.grants:
        if grant.scope.scope_type != "department" or permission not in grant.permissions:
            continue
        row = await db.get(Department, grant.scope.scope_id)
        if (
            row is not None
            and row.company_id == company_id
            and grant.in_force(target=department_target(row), on_date=utcnow().date())
        ):
            clauses.append(Department.path.startswith(row.path, autoescape=True))
    return or_(*clauses) if clauses else false()


async def assignment_filter(db: AsyncSession, current: Actor) -> ColumnElement[bool]:
    if has_permission(current.grants, "role.read", target=ScopePath(), on_date=utcnow().date()):
        return true()
    clauses: list[ColumnElement[bool]] = []
    for grant in current.grants:
        if "role.read" not in grant.permissions:
            continue
        target = await assignment_target(db, grant.scope.scope_type, grant.scope.scope_id)
        if not grant.in_force(target=target, on_date=utcnow().date()):
            continue
        if grant.scope.scope_type == "company":
            departments = select(Department.id).where(Department.company_id == grant.scope.scope_id)
            clauses.append(
                and_(
                    RoleAssignment.scope_type == "company",
                    RoleAssignment.scope_id == grant.scope.scope_id,
                )
            )
        elif grant.scope.scope_type == "department":
            row = await db.get(Department, grant.scope.scope_id)
            assert row is not None
            departments = select(Department.id).where(
                Department.company_id == row.company_id,
                Department.path.startswith(row.path, autoescape=True),
            )
        else:
            continue
        clauses.append(
            and_(
                RoleAssignment.scope_type == "department", RoleAssignment.scope_id.in_(departments)
            )
        )
    return or_(*clauses) if clauses else false()


async def validate_assignment_lifecycle(
    db: AsyncSession, role: Role, subject_type: str, subject_id: uuid.UUID, target: ScopePath
) -> None:
    if not role.is_active:
        raise ValidationFailedError("an inactive role cannot be granted")
    if subject_type == "user":
        user = await db.get(User, subject_id)
        if user is None or user.status == "deactivated":
            raise ValidationFailedError("assignment subject is unavailable")
    else:
        group = await db.get(UserGroup, subject_id)
        if group is None or not group.is_active:
            raise ValidationFailedError("assignment group is unavailable")
    if target.company_id is not None:
        company = await db.get(Company, target.company_id)
        if company is None or company.status != "active":
            raise ValidationFailedError("assignment company is inactive")
    if target.department_id is not None:
        department = await db.get(Department, target.department_id)
        if department is None or not department.is_active:
            raise ValidationFailedError("assignment department is inactive")
