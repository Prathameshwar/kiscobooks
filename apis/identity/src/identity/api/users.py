"""User invite, read, update, deactivation, and IdP links.

A user attaches to the **tenant**, not a company (docs/org-model.md §2.2), so the
object-scope check is against the tenant (``ScopePath()``): managing users is a
tenant-level authority, and a company-scoped grant does not reach it. Cross-tenant
access is impossible regardless — the session filter hides other tenants' rows.

Deactivation **anonymizes, never deletes** (CLAUDE.md invariant 12): the row survives
so the ledger's references stay resolvable, with PII tombstoned in ``domain/``.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.listing import cursor_codec, keyset_page, paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.domain.user_lifecycle import tombstone_values
from identity.models import (
    USER_STATUSES,
    USER_TYPES,
    Company,
    Department,
    Membership,
    User,
    UserIdentity,
)
from identity.schemas.base import Page, PageMeta
from identity.schemas.user import (
    CompanyUserInvite,
    DeactivateRequest,
    UserDetail,
    UserIdentityCreate,
    UserIdentityItem,
    UserInvite,
    UserListItem,
    UserPage,
    UserUpdate,
)

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute, prefix="/v1")

_TENANT = ScopePath()  # users are tenant-level objects
_LIST_SORTS = frozenset({"updated_at", "display_name", "email"})


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    row = await db.get(User, user_id)
    if row is None:
        raise NotFoundError("user not found")
    return row


@router.post("/users", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: UserInvite,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    current.require("user.invite")
    current.require_scope("user.invite", target=_TENANT)

    from identity.services.user_invites import create_invited_user

    return await create_invited_user(db, current, body, request.app.state.settings)


@router.get("/companies/{company_id}/users", response_model=UserPage)
async def list_company_users(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=100),
    user_status: str | None = Query(None, alias="status", enum=sorted(USER_STATUSES)),
    sort: str = "-updated_at",
) -> UserPage:
    from identity.api.common import load_company
    from identity.services.company_people import company_people

    current.require("user.read")
    await load_company(db, company_id)
    current.require_scope("user.read", target=ScopePath(company_id=company_id))
    statement = company_people(company_id)
    if user_status is not None:
        if user_status not in USER_STATUSES:
            raise ValidationFailedError("invalid filter", fields={"status": "unknown value"})
        statement = statement.where(User.status == user_status)
    if q:
        statement = statement.where(
            or_(
                User.email.startswith(q, autoescape=True),
                User.display_name.startswith(q, autoescape=True),
            )
        )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=User,
        projection=UserListItem,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=_LIST_SORTS,
        default="-updated_at",
        codec=cursor_codec(request, f"company-users:{company_id}"),
    )
    return UserPage(
        items=[UserListItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/companies/{company_id}/users/{user_id}", response_model=UserListItem)
async def get_company_user(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    from identity.api.common import load_company
    from identity.services.company_people import company_people

    current.require("user.read")
    await load_company(db, company_id)
    current.require_scope("user.read", target=ScopePath(company_id=company_id))
    row = await db.scalar(company_people(company_id).where(User.id == user_id))
    if row is None:
        raise NotFoundError("company user not found")
    return row


@router.post(
    "/companies/{company_id}/users",
    response_model=UserListItem,
    status_code=status.HTTP_201_CREATED,
)
async def invite_company_user(
    company_id: uuid.UUID,
    body: CompanyUserInvite,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    from identity.api.common import load_company
    from identity.services.user_invites import create_invited_user

    current.require("user.invite")
    company = await load_company(db, company_id)
    current.require_scope("user.invite", target=ScopePath(company_id=company_id))
    if company.status != "active":
        raise ConflictError("company is inactive")
    row = await create_invited_user(
        db,
        current,
        UserInvite(**body.model_dump(), default_company_id=company_id),
        request.app.state.settings,
    )
    now = utcnow()
    membership = Membership(
        id=uuid7(),
        tenant_id=current.tenant_id,
        user_id=row.id,
        company_id=company_id,
        department_id=None,
        is_primary=True,
        started_on=now.date(),
        ended_on=None,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(membership)
    emit(
        db,
        aggregate_type="membership",
        aggregate_id=membership.id,
        event_type="membership.created",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="membership.created",
            entity_type="membership",
            entity_id=membership.id,
            actor_user_id=current.user_id,
            category="admin",
            company_id=company_id,
        ),
    )
    await db.flush()
    return row


@router.get("/users/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> User:
    current.require("user.read")
    row = await _load_user(db, user_id)
    current.require_scope("user.read", target=_TENANT)
    return row


@router.patch("/users/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    current.require("user.update")
    row = await _load_user(db, user_id)
    current.require_scope("user.update", target=_TENANT)
    if row.status == "deactivated":
        raise ConflictError("a deactivated user cannot be edited")

    incoming = body.model_dump(exclude_unset=True)
    if "reporting_manager_id" in incoming and incoming["reporting_manager_id"] is not None:
        manager = await db.get(User, incoming["reporting_manager_id"])
        if manager is None or manager.status != "active":
            raise ValidationFailedError(
                "unknown manager", fields={"reporting_manager_id": "not found in this tenant"}
            )
    company_id = incoming.get("default_company_id", row.default_company_id)
    department_id = incoming.get("default_department_id", row.default_department_id)
    if "default_company_id" in incoming or "default_department_id" in incoming:
        if company_id is not None:
            company = await db.get(Company, company_id)
            if company is None or company.status != "active":
                raise ValidationFailedError(
                    "invalid default company",
                    fields={"default_company_id": "must be active in this tenant"},
                )
        if department_id is not None:
            department = await db.get(Department, department_id)
            if (
                department is None
                or not department.is_active
                or department.company_id != company_id
            ):
                raise ValidationFailedError(
                    "invalid default department",
                    fields={"default_department_id": "must be active in the default company"},
                )
    changes: dict[str, dict[str, Any]] = {}
    for name, value in incoming.items():
        before = getattr(row, name)
        if before != value:
            changes[name] = {
                "from": str(before) if before is not None else None,
                "to": str(value) if value is not None else None,
            }
            setattr(row, name, value)
    if changes:
        row.updated_at = utcnow()
        row.updated_by = current.user_id
        emit(
            db,
            aggregate_type="user",
            aggregate_id=row.id,
            event_type="user.updated",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                action="user.updated",
                entity_type="user",
                entity_id=row.id,
                actor_user_id=current.user_id,
                category="admin",
                changes=changes,
            ),
        )
        await db.flush()
    return row


@router.get("/users", response_model=UserPage)
async def list_users(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    user_status: str | None = Query(None, alias="status", enum=sorted(USER_STATUSES)),
    user_type: str | None = Query(None, enum=sorted(USER_TYPES)),
    q: str | None = Query(None, min_length=2, max_length=100),
    sort: str = "-updated_at",
) -> UserPage:
    current.require("user.read")
    current.require_scope("user.read", target=_TENANT)
    if user_status is not None and user_status not in USER_STATUSES:
        raise ValidationFailedError("invalid filter", fields={"status": "unknown value"})
    if user_type is not None and user_type not in USER_TYPES:
        raise ValidationFailedError("invalid filter", fields={"user_type": "unknown value"})
    statement = select(User)
    if user_status:
        statement = statement.where(User.status == user_status)
    if user_type:
        statement = statement.where(User.user_type == user_type)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            or_(
                User.email.like(f"{escaped}%", escape="\\"),
                User.display_name.like(f"{escaped}%", escape="\\"),
            )
        )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=User,
        projection=UserListItem,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=_LIST_SORTS,
        default="-updated_at",
        codec=cursor_codec(request, "users"),
    )
    return UserPage(
        items=[UserListItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.post("/users/{user_id}/deactivate", response_model=UserDetail)
async def deactivate_user(
    user_id: uuid.UUID,
    body: DeactivateRequest | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    current.require("user.deactivate")
    row = await _load_user(db, user_id)
    current.require_scope("user.deactivate", target=_TENANT)
    if user_id == current.user_id:
        raise ConflictError("you cannot deactivate your own account")
    if row.status == "deactivated":
        return row  # idempotent: already tombstoned

    now = utcnow()
    for name, value in tombstone_values(
        user_id, deactivated_by=current.user_id, now=now, reason=body.reason if body else None
    ).items():
        setattr(row, name, value)
    row.updated_at = now
    row.updated_by = current.user_id
    emit(
        db,
        aggregate_type="user",
        aggregate_id=row.id,
        event_type="user.deactivated",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="user.deactivated",
            entity_type="user",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="security",
            reason=body.reason if body else None,
        ),
    )
    await db.flush()
    return row


@router.post(
    "/users/{user_id}/identities",
    response_model=UserIdentityItem,
    status_code=status.HTTP_201_CREATED,
)
async def link_identity(
    user_id: uuid.UUID,
    body: UserIdentityCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserIdentity:
    # Authentik owns social connections. Its signed linked_identities mapping is
    # authoritative; neither a profile editor nor arbitrary subject text is proof. The local
    # provider has no social connections, so there is nothing a link could be proven against.
    if request.app.state.settings.auth_provider == "local":
        raise ConflictError("Linked sign-in methods are not available with local sign-in.")
    user = await _load_user(db, user_id)
    claims = getattr(request.state, "verified_claims", None)
    if (
        user_id != current.user_id
        or claims is None
        or claims.auth_time is None
        or not 0 <= time.time() - claims.auth_time <= 300
    ):
        raise PermissionDeniedError("linking requires fresh authentication by the account owner")
    owned = {(item.provider, item.subject) for item in claims.linked_identities}
    owned.add(("authentik", claims.sub))
    if (body.provider, body.provider_sub) not in owned or user.authentik_sub != claims.sub:
        raise PermissionDeniedError("provider ownership was not verified")
    now = utcnow()
    row = UserIdentity(
        id=uuid7(),
        tenant_id=current.tenant_id,
        user_id=user_id,
        provider=body.provider,
        provider_sub=body.provider_sub,
        linked_at=now,
        last_login_at=None,
    )
    db.add(row)
    emit(
        db,
        aggregate_type="user_identity",
        aggregate_id=row.id,
        event_type="user.identity_linked",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="user.identity_linked",
            entity_type="user_identity",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="security",
        ),
    )
    await db.flush()
    return row


@router.get("/users/{user_id}/identities", response_model=Page[UserIdentityItem])
async def list_identities(
    user_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[UserIdentityItem]:
    current.require("user.read")
    await _load_user(db, user_id)
    current.require_scope("user.read", target=_TENANT)
    return await paged(
        db,
        request,
        select(UserIdentity).where(UserIdentity.user_id == user_id),
        model=UserIdentity,
        schema=UserIdentityItem,
        limit=limit,
        cursor=cursor,
    )


@router.delete("/users/{user_id}/identities/{identity_id}", status_code=204)
async def unlink_identity(
    user_id: uuid.UUID,
    identity_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    # Self-service inventory unlink; primary Authentik authentication is never removed here.
    if current.user_id != user_id:
        raise PermissionDeniedError("only the account owner can unlink an identity")
    claims = getattr(request.state, "verified_claims", None)
    if claims is None or claims.auth_time is None or not 0 <= time.time() - claims.auth_time <= 300:
        raise PermissionDeniedError("fresh provider authentication is required")
    user = await _load_user(db, user_id)
    row = await db.get(UserIdentity, identity_id)
    if row is None:
        return Response(status_code=204)
    if row.user_id != user_id:
        raise NotFoundError("identity not found")
    if user.authentik_sub is None or (
        row.provider == "authentik" and row.provider_sub == user.authentik_sub
    ):
        raise ConflictError("the primary login method cannot be removed")
    from identity.services.audit import record

    record(db, current, action="user.identity_unlinked", entity="user_identity", entity_id=row.id)
    await db.delete(row)
    return Response(status_code=204)
