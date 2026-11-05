"""Org structure: departments (with materialized-path maintenance), user groups and
their members, and memberships.

Departments and memberships are company-scoped objects; user groups are tenant-scoped.
A department's ``path`` is maintained here — computed on create and rewritten across the
whole moved subtree on reparent, via the pure helpers in ``domain/department_tree`` — so
ancestor-or-self scope resolution stays an indexed prefix test.
"""

from __future__ import annotations

import uuid
from typing import Literal

from billing_platform.authz import ScopePath, has_permission
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor
from identity.api.common import load_company as _load_company
from identity.api.dependencies import session
from identity.api.listing import cursor_codec, keyset_page, paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import department_filter, department_target, guard_group_join
from identity.domain import department_tree
from identity.models import (
    Department,
    Membership,
    User,
    UserGroup,
    UserGroupMember,
)
from identity.schemas.base import Page, PageMeta
from identity.schemas.company import FieldSet
from identity.schemas.org import (
    DepartmentCreate,
    DepartmentItem,
    DepartmentListItem,
    DepartmentPage,
    DepartmentReparent,
    DepartmentUpdate,
    GroupMemberAdd,
    GroupMemberItem,
    GroupMemberListItem,
    MembershipCreate,
    MembershipItem,
    UserGroupCreate,
    UserGroupItem,
    UserGroupListItem,
)
from identity.services.authz_cache import schedule_invalidation
from identity.services.organisation_forms import form_fields

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute, prefix="/v1")

_TENANT = ScopePath()
_DEPT_SORTS = frozenset({"path", "code"})


async def _load_department(
    db: AsyncSession, company_id: uuid.UUID, dept_id: uuid.UUID
) -> Department:
    row = await db.get(Department, dept_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("department not found")
    return row


# --- departments --------------------------------------------------------------


@router.post(
    "/companies/{company_id}/departments",
    response_model=DepartmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    company_id: uuid.UUID,
    body: DepartmentCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Department:
    current.require("department.manage")
    company = await _load_company(db, company_id)
    if company.status != "active":
        raise ConflictError("company is inactive")
    parent_path: str | None = None
    if body.parent_id is not None:
        parent = await _load_department(db, company_id, body.parent_id)
        if not parent.is_active:
            raise ValidationFailedError("parent department is inactive")
        parent_path = parent.path
    target = (
        ScopePath(company_id=company_id) if body.parent_id is None else department_target(parent)
    )
    current.require_scope("department.manage", target=target)
    if body.head_user_id is not None:
        head = await db.get(User, body.head_user_id)
        if head is None or head.status != "active":
            raise ValidationFailedError("invalid head", fields={"head_user_id": "must be active"})
    if (
        await db.scalar(
            select(Department.id).where(
                Department.company_id == company_id, Department.code == body.code
            )
        )
        is not None
    ):
        raise ConflictError("a department with this code already exists in the company")

    dept_id = uuid7()
    path = department_tree.child_path(parent_path, dept_id)
    department_tree.assert_within_depth(path)
    now = utcnow()
    row = Department(
        id=dept_id,
        tenant_id=current.tenant_id,
        company_id=company_id,
        parent_id=body.parent_id,
        code=body.code,
        name=body.name,
        cost_centre_code=body.cost_centre_code,
        head_user_id=body.head_user_id,
        path=path,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    emit(
        db,
        aggregate_type="department",
        aggregate_id=row.id,
        event_type="department.created",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            department_id=row.id,
            company_id=company_id,
            action="department.created",
            entity_type="department",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/departments", response_model=DepartmentPage)
async def list_departments(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    sort: str = "path",
    q: str | None = Query(None, min_length=2, max_length=20),
    department_id: uuid.UUID | None = Query(None, alias="id"),
    is_active: bool | None = None,
) -> DepartmentPage:
    current.require("department.read")
    await _load_company(db, company_id)
    statement = select(Department).where(
        Department.company_id == company_id,
        await department_filter(db, current, "department.read", company_id),
    )
    if q:
        statement = statement.where(Department.code.startswith(q, autoescape=True))
    if department_id is not None:
        statement = statement.where(Department.id == department_id)
    if is_active is not None:
        statement = statement.where(Department.is_active == is_active)
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=Department,
        projection=DepartmentListItem,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=_DEPT_SORTS,
        default="path",
        codec=cursor_codec(request, "departments"),
    )
    return DepartmentPage(
        items=[DepartmentListItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/companies/{company_id}/departments/field-set", response_model=FieldSet)
async def department_fields(
    company_id: uuid.UUID,
    operation: Literal["create", "update"] = "create",
    department_id: uuid.UUID | None = Query(None, alias="id"),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> FieldSet:
    company = await _load_company(db, company_id)
    row = await _load_department(db, company_id, department_id) if department_id else None
    target = department_target(row) if row else ScopePath(company_id=company_id)
    if row:
        current.require_scope("department.read", target=target)
    else:
        current.require("department.manage" if operation == "create" else "department.read")
        # Department-only actors may create under their authorized parent. The
        # create route independently verifies that parent and the destination.
        current.require_scope(
            "department.manage" if operation == "create" else "department.read", target=target
        )
    writable = (
        company.status == "active"
        and (row is None or row.is_active)
        and has_permission(
            current.grants,
            "department.manage",
            target=target,
            on_date=utcnow().date(),
        )
    )
    return form_fields(
        DepartmentCreate if operation == "create" else DepartmentUpdate,
        "identity.department",
        "Department",
        writable,
    )


@router.get("/companies/{company_id}/departments/{department_id}", response_model=DepartmentItem)
async def get_department(
    company_id: uuid.UUID,
    department_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Department:
    current.require("department.read")
    await _load_company(db, company_id)
    row = await _load_department(db, company_id, department_id)
    current.require_scope("department.read", target=department_target(row))
    return row


@router.patch("/companies/{company_id}/departments/{department_id}", response_model=DepartmentItem)
async def update_department(
    company_id: uuid.UUID,
    department_id: uuid.UUID,
    body: DepartmentUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Department:
    current.require("department.manage")
    company = await _load_company(db, company_id)
    row = await _load_department(db, company_id, department_id)
    current.require_scope("department.manage", target=department_target(row))
    if company.status != "active" or not row.is_active:
        raise ConflictError("editing requires an active company and department")
    if body.head_user_id is not None:
        head = await db.get(User, body.head_user_id)
        if head is None or head.status != "active":
            raise ValidationFailedError(
                "invalid department head", fields={"head_user_id": "must be active in this tenant"}
            )
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    row.updated_at = utcnow()
    row.updated_by = current.user_id
    emit(
        db,
        aggregate_type="department",
        aggregate_id=row.id,
        event_type="department.updated",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            department_id=row.id,
            action="department.updated",
            entity_type="department",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
            company_id=company_id,
        ),
    )
    await db.flush()
    return row


@router.post(
    "/companies/{company_id}/departments/{department_id}/reparent", response_model=DepartmentItem
)
async def reparent_department(
    company_id: uuid.UUID,
    department_id: uuid.UUID,
    body: DepartmentReparent,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Department:
    current.require("department.manage")
    company = await _load_company(db, company_id)
    if company.status != "active":
        raise ConflictError("company is inactive")
    dept = await _load_department(db, company_id, department_id)
    current.require_scope("department.manage", target=department_target(dept))
    if not dept.is_active:
        raise ConflictError("reactivate the department before changing its parent")

    new_parent_path: str | None = None
    if body.parent_id is not None:
        if body.parent_id == department_id:
            raise ValidationFailedError("a department cannot be its own parent")
        parent = await _load_department(db, company_id, body.parent_id)
        if not parent.is_active:
            raise ConflictError("parent department is inactive")
        if department_tree.would_create_cycle(moving_path=dept.path, new_parent_path=parent.path):
            raise ConflictError("cannot move a department under one of its own descendants")
        new_parent_path = parent.path

    destination = (
        ScopePath(company_id=company_id) if body.parent_id is None else department_target(parent)
    )
    current.require_scope("department.manage", target=destination)
    old_prefix = dept.path
    new_prefix = department_tree.child_path(new_parent_path, dept.id)
    # Rewrite the moved subtree (self + descendants). LIKE is safe: paths are hex+slash.
    subtree = (
        await db.scalars(
            select(Department).where(
                Department.company_id == company_id, Department.path.like(f"{old_prefix}%")
            )
        )
    ).all()
    now = utcnow()
    for node in subtree:
        node.path = department_tree.rewritten_path(
            old_prefix=old_prefix, new_prefix=new_prefix, path=node.path
        )
        department_tree.assert_within_depth(node.path)
        node.updated_at = now
        node.updated_by = current.user_id
    dept.parent_id = body.parent_id
    emit(
        db,
        aggregate_type="department",
        aggregate_id=dept.id,
        event_type="department.reparented",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            department_id=dept.id,
            company_id=company_id,
            action="department.reparented",
            entity_type="department",
            entity_id=dept.id,
            actor_user_id=current.user_id,
            category="admin",
            changes={"path": {"from": old_prefix, "to": new_prefix}},
        ),
    )
    await db.flush()
    return dept


# --- user groups --------------------------------------------------------------


@router.post("/user-groups", response_model=UserGroupItem, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: UserGroupCreate, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> UserGroup:
    current.require("group.manage")
    current.require_scope("group.manage", target=_TENANT)
    if await db.scalar(select(UserGroup.id).where(UserGroup.code == body.code)) is not None:
        raise ConflictError("a group with this code already exists")
    now = utcnow()
    row = UserGroup(
        id=uuid7(),
        tenant_id=current.tenant_id,
        code=body.code,
        name=body.name,
        description=body.description,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    emit(
        db,
        aggregate_type="user_group",
        aggregate_id=row.id,
        event_type="user_group.created",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="user_group.created",
            entity_type="user_group",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    await db.flush()
    return row


@router.get("/user-groups", response_model=Page[UserGroupListItem])
async def list_groups(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=40),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    sort: str = "id",
    is_active: bool | None = None,
    group_id: uuid.UUID | None = Query(None, alias="id"),
) -> Page[UserGroupListItem]:
    current.require("group.read")
    current.require_scope("group.read", target=_TENANT)
    statement = select(UserGroup)
    if q:
        statement = statement.where(UserGroup.code.startswith(q, autoescape=True))
    if is_active is not None:
        statement = statement.where(UserGroup.is_active == is_active)
    if group_id is not None:
        statement = statement.where(UserGroup.id == group_id)
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=UserGroup,
        projection=UserGroupListItem,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=frozenset({"id", "code"}),
        default="id",
        codec=cursor_codec(request, "user_group"),
    )
    return Page[UserGroupListItem](
        items=[UserGroupListItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/user-groups/field-set", response_model=FieldSet)
async def group_fields(
    operation: Literal["create", "update"] = "create",
    current: Actor = Depends(actor),
) -> FieldSet:
    from identity.api.lifecycle import GroupUpdate

    current.require_scope("group.manage", target=_TENANT)
    return form_fields(
        UserGroupCreate if operation == "create" else GroupUpdate,
        "identity.user_group",
        "UserGroup",
        True,
    )


@router.get("/user-groups/{group_id}", response_model=UserGroupItem)
async def get_group(
    group_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserGroup:
    current.require_scope("group.read", target=_TENANT)
    row = await db.get(UserGroup, group_id)
    if row is None:
        raise NotFoundError("group not found")
    return row


@router.post(
    "/user-groups/{group_id}/members",
    response_model=GroupMemberItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_member(
    group_id: uuid.UUID,
    body: GroupMemberAdd,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserGroupMember:
    current.require("group.manage")
    current.require_scope("group.manage", target=_TENANT)
    group = await db.get(UserGroup, group_id)
    if group is None or not group.is_active:
        raise NotFoundError("active group not found")
    user = await db.get(User, body.user_id)
    if user is None or user.status not in {"active", "invited"}:
        raise ValidationFailedError(
            "user is unavailable", fields={"user_id": "must be active or invited"}
        )
    if (
        await db.scalar(
            select(UserGroupMember.id).where(
                UserGroupMember.user_group_id == group_id, UserGroupMember.user_id == body.user_id
            )
        )
        is not None
    ):
        raise ConflictError("the user is already a member of this group")
    await guard_group_join(db, current, group_id, body.user_id)
    now = utcnow()
    row = UserGroupMember(
        id=uuid7(),
        tenant_id=current.tenant_id,
        user_group_id=group_id,
        user_id=body.user_id,
        added_by=current.user_id,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    # Group membership feeds a user's group-derived grants; drop their cached grants
    # after commit so the new membership takes effect without waiting out the TTL.
    schedule_invalidation(request, current.tenant_id, body.user_id)
    emit(
        db,
        aggregate_type="user_group",
        aggregate_id=group_id,
        event_type="user_group.member_added",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="user_group.member_added",
            entity_type="user_group_member",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="security",
            changes={"user_id": {"from": None, "to": str(body.user_id)}},
        ),
    )
    await db.flush()
    return row


@router.get("/user-groups/{group_id}/members", response_model=Page[GroupMemberListItem])
async def list_group_members(
    group_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[GroupMemberListItem]:
    current.require("group.read")
    current.require_scope("group.read", target=_TENANT)
    if await db.get(UserGroup, group_id) is None:
        raise NotFoundError("group not found")
    result = await paged(
        db,
        request,
        select(UserGroupMember).where(UserGroupMember.user_group_id == group_id),
        model=UserGroupMember,
        schema=GroupMemberItem,
        limit=limit,
        cursor=cursor,
    )
    names: dict[uuid.UUID, str] = {}
    if has_permission(current.grants, "user.read", target=_TENANT, on_date=utcnow().date()):
        ids = [row.user_id for row in result.items]
        for user_id, name in (
            await db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
        ).all():
            names[user_id] = name
    return Page[GroupMemberListItem](
        items=[
            GroupMemberListItem(
                **row.model_dump(),
                display_name=names.get(row.user_id),
            )
            for row in result.items
        ],
        page=result.page,
    )


# --- memberships --------------------------------------------------------------


@router.post(
    "/companies/{company_id}/memberships",
    response_model=MembershipItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership(
    company_id: uuid.UUID,
    body: MembershipCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Membership:
    current.require("department.manage")
    company = await _load_company(db, company_id)
    if company.status != "active":
        raise ConflictError("company is inactive")
    current.require_scope("department.manage", target=ScopePath(company_id=company_id))
    user = await db.get(User, body.user_id)
    if user is None or user.status not in {"active", "invited"}:
        raise ValidationFailedError(
            "user is unavailable", fields={"user_id": "must be active or invited"}
        )
    if body.department_id is not None:
        department = await _load_department(db, company_id, body.department_id)
        if not department.is_active:
            raise ConflictError("department is inactive")
    duplicate = await db.scalar(
        select(Membership.id).where(
            Membership.user_id == body.user_id,
            Membership.company_id == company_id,
            Membership.department_id == body.department_id,
        )
    )
    if duplicate is not None:
        raise ConflictError("this affiliation already exists")
    if (
        body.is_primary
        and await db.scalar(
            select(Membership.id).where(
                Membership.user_id == body.user_id,
                Membership.is_active.is_(True),
                Membership.is_primary.is_(True),
            )
        )
        is not None
    ):
        raise ConflictError("the user already has an active primary affiliation")
    now = utcnow()
    row = Membership(
        id=uuid7(),
        tenant_id=current.tenant_id,
        user_id=body.user_id,
        company_id=company_id,
        department_id=body.department_id,
        is_primary=body.is_primary,
        started_on=body.started_on,
        ended_on=None,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    if body.is_primary:
        if body.started_on is not None and body.started_on > now.date():
            raise ValidationFailedError("a future affiliation cannot be primary")
        user.default_company_id, user.default_department_id = company_id, body.department_id
        user.updated_by = current.user_id
    db.add(row)
    emit(
        db,
        aggregate_type="membership",
        aggregate_id=row.id,
        event_type="membership.created",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            department_id=row.department_id,
            action="membership.created",
            entity_type="membership",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
            company_id=company_id,
        ),
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/memberships", response_model=Page[MembershipItem])
async def list_memberships(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    user_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> Page[MembershipItem]:
    current.require("department.read")
    await _load_company(db, company_id)
    current.require_scope("department.read", target=ScopePath(company_id=company_id))
    statement = select(Membership).where(Membership.company_id == company_id)
    if user_id is not None:
        statement = statement.where(Membership.user_id == user_id)
    if department_id is not None:
        statement = statement.where(Membership.department_id == department_id)
    if is_active is not None:
        statement = statement.where(Membership.is_active == is_active)
    return await paged(
        db,
        request,
        statement,
        model=Membership,
        schema=MembershipItem,
        limit=limit,
        cursor=cursor,
    )
