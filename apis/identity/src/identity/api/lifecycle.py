"""Explicit organization and access lifecycle actions; all preserve referenced history."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import (
    department_target,
    guard_group_join,
    guard_role_change,
)
from identity.domain.lifecycle import assert_status_transition
from identity.models import (
    Company,
    Department,
    FieldPolicy,
    Membership,
    Role,
    RolePermission,
    User,
    UserGroup,
    UserGroupMember,
)
from identity.schemas.base import StrictModel
from identity.schemas.login import ReasonRequest
from identity.schemas.org import DepartmentItem, MembershipItem, OrgInput, UserGroupItem
from identity.schemas.role import RoleListItem
from identity.schemas.user import UserDetail
from identity.services.audit import record
from identity.services.authz_cache import schedule_invalidation

router = APIRouter(prefix="/v1", route_class=StrictRoute, responses=ERROR_RESPONSES)


class ToggleRequest(ReasonRequest):
    is_active: bool = Field(strict=True)


class CompanyLifecycle(ReasonRequest):
    status: Literal["active", "suspended", "closed"]


class CompanyState(StrictModel):
    id: uuid.UUID
    status: str


class UserLifecycle(ReasonRequest):
    status: Literal["active", "suspended"]


class GroupUpdate(OrgInput):
    nonnullable = frozenset({"name"})
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)


class MembershipEnd(ReasonRequest):
    ended_on: dt.date | None = None


def toggle(row: Department | Role | UserGroup, enabled: bool, current: Actor) -> None:
    row.is_active = enabled
    row.deactivated_at = None if enabled else utcnow()
    row.deactivated_by = None if enabled else current.user_id
    row.updated_by = current.user_id


async def guard_group_change(db: AsyncSession, current: Actor, group_id: uuid.UUID) -> None:
    if (
        await db.scalar(
            select(UserGroupMember.id).where(
                UserGroupMember.user_group_id == group_id,
                UserGroupMember.user_id == current.user_id,
            )
        )
        is not None
    ):
        raise PermissionDeniedError("you cannot change your own access through a group")
    if (
        await db.scalar(
            select(FieldPolicy.id)
            .where(
                FieldPolicy.subject_type == "user_group",
                FieldPolicy.subject_id == group_id,
                FieldPolicy.is_active.is_(True),
            )
            .limit(1)
        )
        is not None
    ):
        current.require_scope("field_policy.manage", target=ScopePath())
    # Check every active or scheduled assignment, even while the group is inactive.
    # No joining user to name here: the subject is the group itself.
    await guard_group_join(db, current, group_id)


@router.patch("/user-groups/{group_id}", response_model=UserGroupItem)
async def update_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserGroup:
    current.require_scope("group.manage", target=ScopePath())
    row = await db.get(UserGroup, group_id)
    if row is None:
        raise NotFoundError("group not found")
    changes = {
        key: {"from": getattr(row, key), "to": value}
        for key, value in body.model_dump(exclude_unset=True).items()
        if getattr(row, key) != value
    }
    for key, change in changes.items():
        setattr(row, key, change["to"])
    if changes:
        row.updated_by = current.user_id
        record(
            db,
            current,
            action="user_group.updated",
            entity="user_group",
            entity_id=row.id,
            changes=changes,
        )
    await db.flush()
    return row


@router.post("/user-groups/{group_id}/lifecycle", response_model=UserGroupItem)
async def group_lifecycle(
    group_id: uuid.UUID,
    body: ToggleRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserGroup:
    current.require_scope("group.manage", target=ScopePath())
    row = await db.get(UserGroup, group_id)
    if row is None:
        raise NotFoundError("group not found")
    await guard_group_change(db, current, group_id)
    if row.is_active != body.is_active:
        toggle(row, body.is_active, current)
        record(
            db,
            current,
            action="user_group.lifecycle_changed",
            entity="user_group",
            entity_id=row.id,
            reason=body.reason,
            changes={"is_active": {"to": body.is_active}},
        )
    await db.flush()
    return row


@router.delete("/user-groups/{group_id}/members/{user_id}", status_code=204)
async def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    current.require_scope("group.manage", target=ScopePath())
    if await db.get(UserGroup, group_id) is None:
        raise NotFoundError("group not found")
    if user_id == current.user_id:
        raise PermissionDeniedError("you cannot change your own group membership")
    await guard_group_change(db, current, group_id)
    row = await db.scalar(
        select(UserGroupMember).where(
            UserGroupMember.user_group_id == group_id,
            UserGroupMember.user_id == user_id,
        )
    )
    if row is not None:
        # Only the unreferenced association is removed; the group, user and audit history remain.
        record(
            db,
            current,
            action="user_group.member_removed",
            entity="user_group_member",
            entity_id=row.id,
            changes={"user_id": {"from": str(user_id), "to": None}},
        )
        await db.delete(row)
        await db.flush()
        # Losing group membership can narrow the user's grants; invalidate their cached
        # grants after commit so the removal is not delayed by the TTL.
        schedule_invalidation(request, current.tenant_id, user_id)
    return Response(status_code=204)


async def membership_scope(db: AsyncSession, row: Membership) -> ScopePath:
    if row.department_id is None:
        return ScopePath(company_id=row.company_id)
    department = await db.get(Department, row.department_id)
    if department is None:
        raise ConflictError("membership department is unavailable")
    return department_target(department)


@router.post("/memberships/{membership_id}/end", response_model=MembershipItem)
async def end_membership(
    membership_id: uuid.UUID,
    body: MembershipEnd,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Membership:
    row = await db.get(Membership, membership_id)
    if row is None:
        raise NotFoundError("membership not found")
    current.require_scope("department.manage", target=await membership_scope(db, row))
    ended = body.ended_on or utcnow().date()
    if ended > utcnow().date() or (row.started_on is not None and ended < row.started_on):
        raise ValidationFailedError("membership end must be between its start and today")
    if row.is_active:
        user = await db.get(User, row.user_id, with_for_update=True)
        if user is not None and row.is_primary:
            user.default_company_id = user.default_department_id = None
            user.updated_by = current.user_id
        row.is_active, row.is_primary, row.ended_on = False, False, ended
        row.deactivated_at, row.deactivated_by, row.updated_by = (
            utcnow(),
            current.user_id,
            current.user_id,
        )
        record(
            db,
            current,
            action="membership.ended",
            entity="membership",
            entity_id=row.id,
            company_id=row.company_id,
            department_id=row.department_id,
            reason=body.reason,
        )
    await db.flush()
    return row


@router.post("/memberships/{membership_id}/make-primary", response_model=MembershipItem)
async def make_primary(
    membership_id: uuid.UUID,
    body: ReasonRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Membership:
    row = await db.get(Membership, membership_id)
    if row is None:
        raise NotFoundError("membership not found")
    current.require_scope("department.manage", target=await membership_scope(db, row))
    user = await db.get(User, row.user_id, with_for_update=True)
    company = await db.get(Company, row.company_id)
    department = await db.get(Department, row.department_id) if row.department_id else None
    if (
        not row.is_active
        or row.ended_on is not None
        or user is None
        or user.status != "active"
        or company is None
        or company.status != "active"
        or (department is not None and not department.is_active)
        or (row.started_on is not None and row.started_on > utcnow().date())
    ):
        raise ConflictError("primary membership target is unavailable")
    previous = await db.scalar(
        select(Membership).where(
            Membership.user_id == row.user_id,
            Membership.is_active.is_(True),
            Membership.is_primary.is_(True),
        )
    )
    if previous is not None:
        current.require_scope("department.manage", target=await membership_scope(db, previous))
    if previous is not row:
        if previous is not None:
            previous.is_primary, previous.updated_by = False, current.user_id
            await db.flush()  # release the generated unique key before setting the new primary
        row.is_primary, row.updated_by = True, current.user_id
        user.default_company_id, user.default_department_id = row.company_id, row.department_id
        user.updated_by = current.user_id
        record(
            db,
            current,
            action="membership.primary_changed",
            entity="membership",
            entity_id=row.id,
            company_id=row.company_id,
            department_id=row.department_id,
            reason=body.reason,
            changes={"user_id": {"to": str(row.user_id)}},
        )
    await db.flush()
    return row


@router.post("/companies/{company_id}/lifecycle", response_model=CompanyState)
async def company_lifecycle(
    company_id: uuid.UUID,
    body: CompanyLifecycle,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Company:
    current.require_scope("company.deactivate", target=ScopePath(company_id=company_id))
    row = await db.get(Company, company_id, with_for_update=True)
    if row is None:
        raise NotFoundError("company not found")
    assert_status_transition(row.status, body.status, terminal="closed")
    if row.status != body.status:
        previous = row.status
        row.status, row.updated_by = body.status, current.user_id
        record(
            db,
            current,
            action="company.lifecycle_changed",
            entity="company",
            entity_id=row.id,
            company_id=row.id,
            reason=body.reason,
            changes={"status": {"from": previous, "to": body.status}},
        )
    await db.flush()
    return row


@router.post(
    "/companies/{company_id}/departments/{department_id}/lifecycle", response_model=DepartmentItem
)
async def department_lifecycle(
    company_id: uuid.UUID,
    department_id: uuid.UUID,
    body: ToggleRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Department:
    row = await db.get(Department, department_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("department not found")
    current.require_scope("department.manage", target=department_target(row))
    if row.is_active != body.is_active:
        if not body.is_active:
            if (
                await db.scalar(
                    select(Department.id)
                    .where(
                        Department.parent_id == row.id,
                        Department.is_active.is_(True),
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("deactivate active child departments first")
        else:
            company = await db.get(Company, company_id)
            parent = await db.get(Department, row.parent_id) if row.parent_id else None
            if (
                company is None
                or company.status != "active"
                or (parent is not None and not parent.is_active)
            ):
                raise ConflictError("reactivation requires an active company and parent")
        toggle(row, body.is_active, current)
        record(
            db,
            current,
            action="department.lifecycle_changed",
            entity="department",
            entity_id=row.id,
            company_id=company_id,
            department_id=row.id,
            reason=body.reason,
            changes={"is_active": {"to": body.is_active}},
        )
    await db.flush()
    return row


@router.post("/roles/{role_id}/lifecycle", response_model=RoleListItem)
async def role_lifecycle(
    role_id: uuid.UUID,
    body: ToggleRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Role:
    current.require_scope("role.manage", target=ScopePath())
    role = await db.get(Role, role_id)
    if role is None:
        raise NotFoundError("role not found")
    if role.is_system:
        raise ValidationFailedError("system roles are immutable")
    permissions = frozenset(
        await db.scalars(
            select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
        )
    )
    await guard_role_change(db, current, role.id, permissions)
    if role.is_active != body.is_active:
        toggle(role, body.is_active, current)
        record(
            db,
            current,
            action="role.lifecycle_changed",
            entity="role",
            entity_id=role.id,
            reason=body.reason,
            changes={"is_active": {"to": body.is_active}},
        )
    await db.flush()
    return role


@router.post("/users/{user_id}/lifecycle", response_model=UserDetail)
async def user_lifecycle(
    user_id: uuid.UUID,
    body: UserLifecycle,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    current.require_scope("user.deactivate", target=ScopePath())
    if user_id == current.user_id:
        raise PermissionDeniedError("you cannot change your own access lifecycle")
    row = await db.get(User, user_id)
    if row is None:
        raise NotFoundError("user not found")
    if row.status not in {"active", "suspended"}:
        raise ConflictError("invited or anonymized users cannot use this transition")
    if row.status != body.status:
        previous = row.status
        row.status, row.tokens_valid_after_at, row.updated_by = (
            body.status,
            utcnow(),
            current.user_id,
        )
        record(
            db,
            current,
            action="user.lifecycle_changed",
            entity="user",
            entity_id=row.id,
            reason=body.reason,
            changes={"status": {"from": previous, "to": body.status}},
        )
    await db.flush()
    return row
