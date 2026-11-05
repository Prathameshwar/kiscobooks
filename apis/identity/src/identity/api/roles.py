"""Roles, their permission composition, and role assignments.

This is the authorization surface, so it is where the escalation guards
(``domain/authorization``) actually run. Composing a role and assigning one both go
through them: you cannot put a permission you do not hold into a role, cannot assign a
role at a scope broader than your own, and cannot change your own assignments — directly
or through a group you belong to (docs/roles-permissions.md §1.5). Every write here is a
``security``-category audit event on the outbox, in the request's transaction.

Permissions are code, roles are data: a role's keys are validated against the catalogue
on write and again at boot; a system role is read-only to every tenant (422 to edit,
clone it instead).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.pagination import PageRequest
from billing_platform.permissions import PERMISSIONS, separation_of_duties_conflicts
from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor, refresh_current
from identity.api.dependencies import session
from identity.api.field_access import CompanyAccess
from identity.api.listing import cursor_codec, keyset_page
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import (
    assignment_actor,
    assignment_filter,
    assignment_target,
    department_target,
    guard_role_change,
    guard_role_fields,
    lock_tenant,
    validate_assignment_lifecycle,
)
from identity.domain import authorization
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import (
    Company,
    Department,
    Role,
    RoleAssignment,
    RolePermission,
    User,
    UserGroup,
)
from identity.schemas.base import PageMeta
from identity.schemas.company import CompanyListItem
from identity.schemas.role import (
    AssignmentCheck,
    AssignmentCreate,
    AssignmentItem,
    AssignmentPage,
    AssignmentRegrant,
    PermissionCatalogue,
    RevokeRequest,
    RoleClone,
    RoleComposed,
    RoleCreate,
    RoleDetail,
    RoleListItem,
    RolePage,
    RoleUpdate,
)
from identity.services.authz_cache import schedule_invalidation

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute, prefix="/v1")

_ROLE_SORTS = frozenset({"updated_at", "name", "key"})
_ASSIGNMENT_SORTS = frozenset({"created_at"})


async def _role_permission_keys(db: AsyncSession, role_id: uuid.UUID) -> list[str]:
    rows = await db.scalars(
        select(RolePermission.permission_key).where(RolePermission.role_id == role_id)
    )
    return sorted(rows.all())


async def _role_detail(db: AsyncSession, role: Role) -> RoleDetail:
    return RoleDetail(
        id=role.id,
        key=role.key,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        scope_hint=role.scope_hint,
        cloned_from_role_id=role.cloned_from_role_id,
        is_active=role.is_active,
        permissions=await _role_permission_keys(db, role.id),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


async def _load_role(db: AsyncSession, role_id: uuid.UUID) -> Role:
    row = await db.get(Role, role_id)
    if row is None:
        raise NotFoundError("role not found")
    return row


_target_for = assignment_target


# --- roles --------------------------------------------------------------------


@router.post("/roles", response_model=RoleComposed, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> RoleComposed:
    current.require("role.manage")
    current.require_scope("role.manage", target=ScopePath())
    today = utcnow().date()
    # Guard 1 at composition time: you cannot compose a role out of permissions you do
    # not hold at tenant scope. Returns SoD pairs to warn on (a tenant may need them).
    warnings = authorization.assert_role_composition_allowed(
        body.permissions, actor=current.as_domain_actor(), target=ScopePath(), on_date=today
    )
    existing = await db.scalar(select(Role.id).where(Role.key == body.key))
    if existing is not None:
        raise ConflictError("a role with this key already exists in this tenant")

    now = utcnow()
    role = Role(
        id=uuid7(),
        tenant_id=current.tenant_id,
        key=body.key,
        name=body.name,
        description=body.description,
        cloned_from_role_id=None,
        scope_hint=body.scope_hint,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(role)
    for key in sorted(set(body.permissions)):
        db.add(
            RolePermission(
                id=uuid7(),
                tenant_id=current.tenant_id,
                role_id=role.id,
                permission_key=key,
                created_at=now,
                created_by=current.user_id,
                updated_at=now,
                updated_by=current.user_id,
            )
        )
    emit(
        db,
        aggregate_type="role",
        aggregate_id=role.id,
        event_type="role.created",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="role.created",
            entity_type="role",
            entity_id=role.id,
            actor_user_id=current.user_id,
            category="security",
            changes={
                "separation_of_duties_warnings": {"from": None, "to": [list(p) for p in warnings]}
            }
            if warnings
            else None,
        ),
    )
    await db.flush()
    return RoleComposed(
        role=await _role_detail(db, role),
        separation_of_duties_warnings=[list(pair) for pair in warnings],
    )


@router.get("/roles/{role_id}", response_model=RoleDetail)
async def get_role(
    role_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> RoleDetail:
    current.require("role.read")
    role = await _load_role(db, role_id)
    return await _role_detail(db, role)


@router.patch("/roles/{role_id}", response_model=RoleComposed)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> RoleComposed:
    current.require("role.manage")
    current.require_scope("role.manage", target=ScopePath())
    role = await _load_role(db, role_id)
    # 422 for every actor: a shipped role is read-only, clone it to customise.
    authorization.assert_role_editable(is_system_role=role.is_system)

    today = utcnow().date()
    before_permissions = frozenset(await _role_permission_keys(db, role_id))
    # A metadata-only edit still reports the pairs the role holds: the console reads
    # this off the PATCH response, and an empty list there reads as "now resolved".
    warnings = separation_of_duties_conflicts(before_permissions)
    if body.permissions is not None:
        requested = frozenset(body.permissions)
        warnings = authorization.assert_role_composition_allowed(
            body.permissions, actor=current.as_domain_actor(), target=ScopePath(), on_date=today
        )
        if requested != before_permissions:
            await guard_role_change(db, current, role_id, before_permissions | requested)
        existing = await db.scalars(select(RolePermission).where(RolePermission.role_id == role_id))
        for row in existing.all():
            await db.delete(row)
        await db.flush()
        now = utcnow()
        for key in sorted(set(body.permissions)):
            db.add(
                RolePermission(
                    id=uuid7(),
                    tenant_id=current.tenant_id,
                    role_id=role_id,
                    permission_key=key,
                    created_at=now,
                    created_by=current.user_id,
                    updated_at=now,
                    updated_by=current.user_id,
                )
            )

    # Collected before the values are applied, so the event carries both sides. Name
    # and description are not on the audit allowlist and become changed-field markers.
    changes: dict[str, Any] = {
        key: {"from": getattr(role, key), "to": value}
        for key, value in (
            ("name", body.name),
            ("description", body.description),
            ("scope_hint", body.scope_hint),
        )
        if value is not None and getattr(role, key) != value
    }
    for key, change in changes.items():
        setattr(role, key, change["to"])
    if body.permissions is not None and frozenset(body.permissions) != before_permissions:
        changes["permissions"] = {
            # The stored set, not the request list: a repeated key would otherwise make
            # the security event disagree with ``role_permission``.
            "from": sorted(before_permissions),
            "to": sorted(frozenset(body.permissions)),
        }
        changes["separation_of_duties_warnings"] = {
            "from": [list(pair) for pair in separation_of_duties_conflicts(before_permissions)],
            "to": [list(pair) for pair in warnings],
        }
    role.updated_at = utcnow()
    role.updated_by = current.user_id
    emit(
        db,
        aggregate_type="role",
        aggregate_id=role.id,
        event_type="role.updated",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="role.updated",
            entity_type="role",
            entity_id=role.id,
            actor_user_id=current.user_id,
            category="security",
            changes=changes or None,
        ),
    )
    await db.flush()
    return RoleComposed(
        role=await _role_detail(db, role),
        separation_of_duties_warnings=[list(pair) for pair in warnings],
    )


@router.post(
    "/roles/{role_id}/clone", response_model=RoleDetail, status_code=status.HTTP_201_CREATED
)
async def clone_role(
    role_id: uuid.UUID,
    body: RoleClone,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> RoleDetail:
    """Clone any role (system or tenant) into an editable tenant role. Cloning grants
    the source's permissions into the copy, so the actor must hold them (guard 1)."""
    current.require("role.manage")
    current.require_scope("role.manage", target=ScopePath())
    source = await _load_role(db, role_id)
    permissions = await _role_permission_keys(db, role_id)
    today = utcnow().date()
    authorization.assert_role_composition_allowed(
        permissions, actor=current.as_domain_actor(), target=ScopePath(), on_date=today
    )
    if await db.scalar(select(Role.id).where(Role.key == body.key)) is not None:
        raise ConflictError("a role with this key already exists in this tenant")

    now = utcnow()
    clone = Role(
        id=uuid7(),
        tenant_id=current.tenant_id,
        key=body.key,
        name=body.name or f"{source.name} (copy)",
        description=source.description,
        cloned_from_role_id=source.id,
        scope_hint=source.scope_hint,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(clone)
    for key in permissions:
        db.add(
            RolePermission(
                id=uuid7(),
                tenant_id=current.tenant_id,
                role_id=clone.id,
                permission_key=key,
                created_at=now,
                created_by=current.user_id,
                updated_at=now,
                updated_by=current.user_id,
            )
        )
    emit(
        db,
        aggregate_type="role",
        aggregate_id=clone.id,
        event_type="role.cloned",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="role.cloned",
            entity_type="role",
            entity_id=clone.id,
            actor_user_id=current.user_id,
            category="security",
            changes={"cloned_from": {"from": None, "to": str(source.id)}},
        ),
    )
    await db.flush()
    return await _role_detail(db, clone)


@router.get("/roles", response_model=RolePage)
async def list_roles(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    scope_hint: Literal["platform", "tenant", "company", "department"] | None = None,
    q: str | None = Query(None, min_length=2, max_length=100),
    sort: str = "name",
) -> RolePage:
    current.require("role.read")
    statement = select(Role)
    if scope_hint:
        statement = statement.where(Role.scope_hint == scope_hint)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            or_(
                Role.key.like(f"{escaped}%", escape="\\"),
                Role.name.like(f"{escaped}%", escape="\\"),
            )
        )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=Role,
        projection=RoleListItem,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=_ROLE_SORTS,
        default="name",
        codec=cursor_codec(request, "roles"),
    )
    return RolePage(
        items=[RoleListItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/permissions", response_model=PermissionCatalogue)
async def list_permissions(current: Actor = Depends(actor)) -> PermissionCatalogue:
    """The fixed permission catalogue a client builds its role-composition form from."""
    current.require("role.read")
    return PermissionCatalogue(permissions=sorted(PERMISSIONS))


# --- assignments --------------------------------------------------------------


def _assignment_item(row: RoleAssignment) -> AssignmentItem:
    return AssignmentItem(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        role_id=row.role_id,
        scope_type=row.scope_type,
        scope_id=None if row.scope_id == SCOPE_ALL else row.scope_id,
        is_active=row.is_active,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        granted_by=row.granted_by,
        grant_reason=row.grant_reason,
        created_at=row.created_at,
    )


def _assert_validity(valid_from: dt.date, valid_to: dt.date | None) -> None:
    if valid_to is not None and valid_to < valid_from:
        raise ValidationFailedError(
            "invalid validity window", fields={"valid_to": "must be on or after valid_from"}
        )


async def _check_assignment(
    db: AsyncSession, current: Actor, body: AssignmentCreate
) -> tuple[Role, ScopePath]:
    current.require("role.assign")
    role = await _load_role(db, body.role_id)
    if body.subject_type == "user" and await db.get(User, body.subject_id) is None:
        raise ValidationFailedError("unknown subject", fields={"subject_id": "no such user"})

    target = await _target_for(db, body.scope_type, body.scope_id)
    await validate_assignment_lifecycle(db, role, body.subject_type, body.subject_id, target)
    permissions = frozenset(await _role_permission_keys(db, role.id))
    today = utcnow().date()
    _assert_validity(body.valid_from or today, body.valid_to)
    change = authorization.AssignmentChange(
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        role_permissions=permissions,
        target=target,
    )
    # All three guards, in the order a denial should be decided: self, then scope, then
    # the contents (the permissions the role grants must be ones the actor holds here).
    authorization.assert_assignment_change_allowed(
        change, actor=await assignment_actor(db, current), on_date=today
    )
    await guard_role_fields(db, current, role.id, target)

    return role, target


@router.post("/role-assignments/check", response_model=AssignmentCheck)
async def check_assignment(
    body: AssignmentCreate, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> AssignmentCheck:
    # A non-mutating preview. The actual grant repeats every check in its own transaction.
    await _check_assignment(db, current, body)
    return AssignmentCheck()


@router.post(
    "/role-assignments", response_model=AssignmentItem, status_code=status.HTTP_201_CREATED
)
async def assign_role(
    body: AssignmentCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AssignmentItem:
    role, target = await _check_assignment(db, current, body)
    today = utcnow().date()

    now = utcnow()
    row = RoleAssignment(
        id=uuid7(),
        tenant_id=current.tenant_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        role_id=role.id,
        scope_type=body.scope_type,
        scope_id=SCOPE_ALL if body.scope_type == "tenant" else body.scope_id,
        granted_by=current.user_id,
        grant_reason=body.grant_reason,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        valid_from=body.valid_from or today,
        valid_to=body.valid_to,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    # A grant to a specific user changes that user's effective permissions now — drop
    # their cached grants after commit so the change does not wait out the TTL. A
    # group-subject grant is bounded by the TTL instead (the agreed v1 scope).
    if row.subject_type == "user":
        schedule_invalidation(request, current.tenant_id, row.subject_id)
    emit(
        db,
        aggregate_type="role_assignment",
        aggregate_id=row.id,
        event_type="role_assignment.granted",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            department_id=target.department_id,
            company_id=target.company_id,
            action="role_assignment.granted",
            entity_type="role_assignment",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="security",
            reason=body.grant_reason,
        ),
    )
    await db.flush()
    return _assignment_item(row)


@router.post("/role-assignments/{assignment_id}/revoke", response_model=AssignmentItem)
async def revoke_assignment(
    assignment_id: uuid.UUID,
    request: Request,
    body: RevokeRequest | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AssignmentItem:
    current.require("role.assign")
    row = await db.get(RoleAssignment, assignment_id)
    if row is None:
        raise NotFoundError("assignment not found")

    # Revocation is guarded identically to granting (docs/roles-permissions.md §1.5):
    # de-escalation for the subject, but revoking the controller's role the evening
    # before a close is an outage on one call, so the same authority is required.
    permissions = frozenset(await _role_permission_keys(db, row.role_id))
    scope_id = None if row.scope_id == SCOPE_ALL else row.scope_id
    change = authorization.AssignmentChange(
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        role_permissions=permissions,
        target=await _target_for(db, row.scope_type, scope_id),
    )
    authorization.assert_assignment_change_allowed(
        change, actor=await assignment_actor(db, current), on_date=utcnow().date()
    )
    await guard_role_fields(db, current, row.role_id, change.target)

    if not row.is_active:
        return _assignment_item(row)

    # Revocation must take effect promptly (CLAUDE.md §5.4). Drop the user's cached
    # grants after commit; the TTL is only the backstop, not the primary path.
    if row.subject_type == "user":
        schedule_invalidation(request, current.tenant_id, row.subject_id)

    now = utcnow()
    row.is_active = False
    row.deactivated_at = now
    row.deactivated_by = current.user_id
    row.updated_at = now
    row.updated_by = current.user_id
    emit(
        db,
        aggregate_type="role_assignment",
        aggregate_id=row.id,
        event_type="role_assignment.revoked",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            department_id=change.target.department_id,
            company_id=change.target.company_id,
            action="role_assignment.revoked",
            entity_type="role_assignment",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="security",
            reason=body.reason if body else None,
        ),
    )
    await db.flush()
    return _assignment_item(row)


@router.get("/role-assignments", response_model=AssignmentPage)
async def list_assignments(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    subject_id: uuid.UUID | None = None,
    subject_type: Literal["user", "user_group"] | None = None,
    role_id: uuid.UUID | None = None,
    scope_type: Literal["tenant", "company", "department"] | None = None,
    active: bool | None = None,
    sort: str = "-created_at",
) -> AssignmentPage:
    current.require("role.read")
    statement = select(RoleAssignment).where(await assignment_filter(db, current))
    if subject_id is not None:
        statement = statement.where(RoleAssignment.subject_id == subject_id)
    if subject_type is not None:
        statement = statement.where(RoleAssignment.subject_type == subject_type)
    if role_id is not None:
        statement = statement.where(RoleAssignment.role_id == role_id)
    if scope_type is not None:
        statement = statement.where(RoleAssignment.scope_type == scope_type)
    if active is not None:
        statement = statement.where(RoleAssignment.is_active == active)
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=RoleAssignment,
        projection=AssignmentItem,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=_ASSIGNMENT_SORTS,
        default="-created_at",
        codec=cursor_codec(request, "role-assignments"),
    )
    return AssignmentPage(
        items=await _assignment_directory_items(db, current, rows),
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


async def _assignment_directory_items(
    db: AsyncSession, current: Actor, rows: list[RoleAssignment]
) -> list[AssignmentItem]:
    """Resolve labels in bounded queries, retaining each directory's read policy."""
    if not rows:
        return []

    def permitted(permission: str, target: ScopePath) -> bool:
        try:
            current.require_scope(permission, target=target)
        except PermissionDeniedError:
            return False
        return True

    roles = {
        row.id: row.name
        for row in await db.scalars(
            select(Role).where(Role.id.in_({item.role_id for item in rows}))
        )
    }
    subjects: dict[uuid.UUID, str] = {}
    user_ids = {row.subject_id for row in rows if row.subject_type == "user"}
    if user_ids and permitted("user.read", ScopePath()):
        subjects.update(
            {
                row.id: row.display_name
                for row in await db.scalars(select(User).where(User.id.in_(user_ids)))
            }
        )
    group_ids = {row.subject_id for row in rows if row.subject_type == "user_group"}
    if group_ids and permitted("group.read", ScopePath()):
        subjects.update(
            {
                row.id: row.name
                for row in await db.scalars(select(UserGroup).where(UserGroup.id.in_(group_ids)))
            }
        )
    scopes: dict[uuid.UUID, str] = {}
    scoped_subjects: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
    company_ids = {row.scope_id for row in rows if row.scope_type == "company"}
    if company_ids:
        company_access = await CompanyAccess.load(db, current)
        scopes.update(
            {
                row.id: str(name)
                for row in await db.scalars(select(Company).where(Company.id.in_(company_ids)))
                if permitted("company.read", ScopePath(company_id=row.id))
                and (name := company_access.project(row, CompanyListItem).get("display_name"))
                is not None
            }
        )
    department_ids = {row.scope_id for row in rows if row.scope_type == "department"}
    departments = (
        list(await db.scalars(select(Department).where(Department.id.in_(department_ids))))
        if department_ids
        else []
    )
    if department_ids:
        scopes.update(
            {
                row.id: row.name
                for row in departments
                if permitted("department.read", department_target(row))
            }
        )
    department_companies = {row.id: row.company_id for row in departments}
    if user_ids and not permitted("user.read", ScopePath()):
        from identity.models import Membership
        from identity.services.company_people import current_company_memberships

        readable_companies = {
            company_id
            for company_id in company_ids | set(department_companies.values())
            if permitted("user.read", ScopePath(company_id=company_id))
        }
        if readable_companies:
            pairs = {
                (department_companies.get(row.scope_id, row.scope_id), row.subject_id)
                for row in rows
                if row.subject_type == "user"
                and department_companies.get(row.scope_id, row.scope_id) in readable_companies
            }
            # At most one projected pair per directory row, even where a person has
            # many department affiliations. Never materialize the whole membership set.
            affiliations = (
                (
                    await db.execute(
                        current_company_memberships(readable_companies)
                        .with_only_columns(Membership.company_id, Membership.user_id)
                        .where(
                            or_(
                                *(
                                    and_(
                                        Membership.company_id == company_id,
                                        Membership.user_id == user_id,
                                    )
                                    for company_id, user_id in pairs
                                )
                            )
                        )
                        .distinct()
                    )
                ).all()
                if pairs
                else []
            )
            names = {
                row.id: row.display_name
                for row in await db.scalars(
                    select(User).where(User.id.in_(user_ids), User.user_type == "tenant_user")
                )
            }
            scoped_subjects = {
                (company_id, user_id): names[user_id]
                for company_id, user_id in affiliations
                if user_id in names
            }
    return [
        _assignment_item(row).model_copy(
            update={
                "role_name": roles.get(row.role_id),
                "subject_label": subjects.get(row.subject_id)
                or scoped_subjects.get(
                    (department_companies.get(row.scope_id, row.scope_id), row.subject_id)
                )
                if row.subject_type == "user"
                else subjects.get(row.subject_id),
                "scope_label": "Whole tenant"
                if row.scope_type == "tenant"
                else scopes.get(row.scope_id),
            }
        )
        for row in rows
    ]


@router.post("/role-assignments/{assignment_id}/regrant", response_model=AssignmentItem)
async def regrant_assignment(
    assignment_id: uuid.UUID,
    body: AssignmentRegrant,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current: Actor = Depends(actor),
) -> AssignmentItem:
    async def load_authorized(db: AsyncSession) -> RoleAssignment:
        current.require("role.assign")
        row = await db.get(RoleAssignment, assignment_id)
        if row is None:
            raise NotFoundError("assignment not found")
        role = await _load_role(db, row.role_id)
        if not role.is_active:
            raise ValidationFailedError("an inactive role cannot be granted")
        change = authorization.AssignmentChange(
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            role_permissions=frozenset(await _role_permission_keys(db, row.role_id)),
            target=await _target_for(db, row.scope_type, row.scope_id),
        )
        await validate_assignment_lifecycle(
            db, role, row.subject_type, row.subject_id, change.target
        )
        authorization.assert_assignment_change_allowed(
            change, actor=await assignment_actor(db, current), on_date=utcnow().date()
        )
        await guard_role_fields(db, current, row.role_id, change.target)
        return row

    async def authorize(db: AsyncSession, references: dict[str, Any] | None) -> None:
        await lock_tenant(db, current.tenant_id)
        await refresh_current(db, request, current)
        from identity.services.step_up import enforce_request

        await enforce_request(db, request, current)
        db.sync_session.info[CAPTURE_KEY] = True
        await load_authorized(db)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await load_authorized(db)
        if row.is_active:
            raise ConflictError("assignment is already active")
        target = await _target_for(db, row.scope_type, row.scope_id)
        before = {
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        }
        _assert_validity(body.valid_from or utcnow().date(), body.valid_to)
        row.valid_from = body.valid_from or utcnow().date()
        row.valid_to = body.valid_to
        row.is_active = True
        row.deactivated_at = None
        row.deactivated_by = None
        row.granted_by = current.user_id
        row.grant_reason = body.reason
        row.updated_at = utcnow()
        row.updated_by = current.user_id
        emit(
            db,
            aggregate_type="role_assignment",
            aggregate_id=row.id,
            event_type="role_assignment.regranted",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                department_id=target.department_id,
                action="role_assignment.regranted",
                entity_type="role_assignment",
                entity_id=row.id,
                actor_user_id=current.user_id,
                category="security",
                company_id=target.company_id,
                reason=body.reason,
                changes={
                    key: {
                        "from": value,
                        "to": getattr(row, key).isoformat() if getattr(row, key) else None,
                    }
                    for key, value in before.items()
                },
            ),
        )
        await db.flush()
        return CommandReceipt(200, {"assignment_id": str(row.id)})

    async def render(db: AsyncSession, references: dict[str, Any]) -> AssignmentItem:
        return _assignment_item(await load_authorized(db))

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            tenant_id=current.tenant_id,
            company_id=None,
            actor_id=current.user_id,
            operation="identity.role_assignment.regrant",
            key=idempotency_key,
            request={"assignment_id": str(assignment_id), **body.model_dump(mode="json")},
        ),
        authorize=authorize,
        mutate=mutate,
        render=render,
    )
    # This path runs its own command transaction rather than the session dependency, so
    # the after-commit hook does not fire here; invalidate directly, post-commit. A
    # re-grant only ever targets the assignment's existing subject.
    if result.value.subject_type == "user":
        cache = getattr(request.app.state, "grant_cache", None)
        if cache is not None:
            await cache.invalidate(current.tenant_id, result.value.subject_id)
    return result.value
