"""Configured platform operators manage only a tenant's fixed administrator assignment."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, refresh_current
from identity.api.listing import cursor_codec, keyset_page
from identity.api.platform import fresh_platform_actor, platform_actor
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import Tenant, User
from identity.schemas.base import Page, PageMeta
from identity.schemas.platform_access import (
    AdministratorCommand,
    AdministratorInvite,
    AdministratorListItem,
    AdministratorReceipt,
    AdministratorRecoveryLink,
    AdministratorRecoveryRequest,
    AdministratorTenant,
    PlatformAdministrator,
    PlatformAdministratorRole,
)
from identity.services import platform_access as access
from identity.services.audit import record
from identity.services.identity_provider import recovery_directory, recovery_supported

router = APIRouter(prefix="/v1/platform/access", route_class=StrictRoute, responses=ERROR_RESPONSES)


async def authorize(
    db: AsyncSession, request: Request, current: Actor, *, write: bool = False
) -> None:
    with tenant_scope(current.tenant_id):
        if write:
            await lock_tenant(db, current.tenant_id)
        await refresh_current(db, request, current)
        current.require_scope(
            "platform.tenant_access.manage" if write else "platform.tenant_access.read",
            target=ScopePath(),
        )


@router.get("/role", response_model=PlatformAdministratorRole)
async def role(
    request: Request, current: Actor = Depends(platform_actor)
) -> PlatformAdministratorRole:
    async with request.app.state.session_factory() as db:
        await authorize(db, request, current)
        return await access.administrator_role(db)


@router.get("/tenants", response_model=Page[AdministratorTenant])
async def tenants(
    request: Request,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=3000),
    current: Actor = Depends(platform_actor),
) -> Page[AdministratorTenant]:
    async with request.app.state.session_factory() as db:
        await authorize(db, request, current)
        # Installation-wide selection is deliberately a lean tenant projection, never user data.
        with unfiltered():
            statement = select(Tenant).where(Tenant.id.not_in([current.tenant_id, SCOPE_ALL]))
            if q:
                statement = statement.where(Tenant.name.istartswith(q, autoescape=True))
            rows, next_cursor, has_more = await keyset_page(
                db,
                statement,
                model=Tenant,
                page=PageRequest(limit, cursor),
                sort="name",
                allowed=frozenset({"name"}),
                default="name",
                codec=cursor_codec(request, "platform-administrator-tenants"),
                projection=AdministratorTenant,
            )
            return Page[AdministratorTenant](
                items=[AdministratorTenant.model_validate(row) for row in rows],
                page=PageMeta(next_cursor=next_cursor, has_more=has_more),
            )


@router.get("/tenants/{tenant_id}", response_model=AdministratorTenant)
async def tenant(
    tenant_id: uuid.UUID, request: Request, current: Actor = Depends(platform_actor)
) -> AdministratorTenant:
    async with request.app.state.session_factory() as db:
        await authorize(db, request, current)
        with tenant_scope(tenant_id):
            return AdministratorTenant.model_validate(
                await access.target_tenant(db, tenant_id, current)
            )


@router.get("/tenants/{tenant_id}/administrators", response_model=Page[AdministratorListItem])
async def administrators(
    tenant_id: uuid.UUID,
    request: Request,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    status: Literal["active", "invited", "suspended", "deactivated"] | None = None,
    sort: str = "display_name",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=3000),
    current: Actor = Depends(platform_actor),
) -> Page[AdministratorListItem]:
    async with request.app.state.session_factory() as db, db.begin():
        await authorize(db, request, current)
        role = await access.administrator_role(db)
        with tenant_scope(tenant_id):
            await access.target_tenant(db, tenant_id, current)
            statement = access.administrator_users(tenant_id, role.id)
            if q:
                statement = statement.where(User.display_name.istartswith(q, autoescape=True))
            if status:
                statement = statement.where(User.status == status)
            rows, next_cursor, has_more = await keyset_page(
                db,
                statement,
                model=User,
                page=PageRequest(limit, cursor),
                sort=sort,
                allowed=frozenset({"display_name", "email", "updated_at"}),
                default="display_name",
                codec=cursor_codec(request, "platform-administrators"),
                projection=AdministratorListItem,
            )
            result = Page[AdministratorListItem](
                items=[AdministratorListItem.model_validate(row) for row in rows],
                page=PageMeta(next_cursor=next_cursor, has_more=has_more),
            )
        with tenant_scope(current.tenant_id):
            record(
                db,
                current,
                action="platform.tenant_administrators_read",
                entity="tenant",
                entity_id=tenant_id,
            )
        return result


@router.get("/tenants/{tenant_id}/administrators/{user_id}", response_model=PlatformAdministrator)
async def administrator(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(platform_actor),
) -> PlatformAdministrator:
    async with request.app.state.session_factory() as db, db.begin():
        await authorize(db, request, current)
        role = await access.administrator_role(db)
        with tenant_scope(tenant_id):
            tenant = await access.target_tenant(db, tenant_id, current)
            row, assignment = await access.administrator(db, tenant_id, role.id, user_id)
            result = await access.detail(db, tenant, row, assignment, request.app.state.settings)
        with tenant_scope(current.tenant_id):
            record(
                db,
                current,
                action="platform.tenant_administrator_read",
                entity="tenant",
                entity_id=tenant_id,
                changes={"administrator_id": str(user_id)},
            )
        return result


async def command(
    request: Request,
    current: Actor,
    tenant_id: uuid.UUID,
    body: AdministratorInvite | AdministratorCommand,
    key: str,
    user_id: uuid.UUID | None = None,
) -> AdministratorReceipt:
    async def check(db: AsyncSession, references: dict[str, Any] | None) -> None:
        await authorize(db, request, current, write=True)
        role = await access.administrator_role(db)
        with tenant_scope(tenant_id):
            await access.target_tenant(db, tenant_id, current, write=True)
            checked_id = user_id or (
                uuid.UUID(references["administrator_id"]) if references else None
            )
            if checked_id:
                await access.administrator(db, tenant_id, role.id, checked_id)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        db.sync_session.info[CAPTURE_KEY] = True
        role = await access.administrator_role(db)
        with tenant_scope(tenant_id):
            tenant = await access.target_tenant(db, tenant_id, current, write=True)
            if isinstance(body, AdministratorInvite):
                result = await access.invite(
                    db, current, tenant, role, body, request.app.state.settings
                )
                action = "invited"
            else:
                if user_id is None:
                    raise NotFoundError("tenant administrator not found")
                row, assignment = await access.administrator(db, tenant_id, role.id, user_id)
                result = await access.change(
                    db, current, row, assignment, body, request.app.state.settings
                )
                action = body.action
        with tenant_scope(current.tenant_id):
            record(
                db,
                current,
                action="platform.tenant_administrator_" + action,
                entity="tenant",
                entity_id=tenant_id,
                changes={
                    "administrator_id": str(result.administrator_id),
                    "assignment_id": str(result.assignment_id),
                    "status": result.status,
                    "is_active": result.assignment_active,
                },
            )
        return CommandReceipt(
            201 if isinstance(body, AdministratorInvite) else 200, result.model_dump(mode="json")
        )

    async def render(db: AsyncSession, references: dict[str, Any]) -> AdministratorReceipt:
        return AdministratorReceipt.model_validate(references)

    with tenant_scope(current.tenant_id):
        result = await execute_idempotent(
            request.app.state.session_factory,
            CommandIdentity(
                current.tenant_id,
                None,
                current.user_id,
                "identity.platform.tenant_administrator."
                + ("invite" if isinstance(body, AdministratorInvite) else "change"),
                key,
                {
                    "tenant_id": str(tenant_id),
                    "administrator_id": str(user_id) if user_id else None,
                    "body": body.model_dump(mode="json"),
                },
            ),
            authorize=check,
            mutate=mutate,
            render=render,
        )
    cache = getattr(request.app.state, "grant_cache", None)
    if cache is not None:
        await cache.invalidate(tenant_id, result.value.administrator_id)
    return result.value


@router.post(
    "/tenants/{tenant_id}/administrators", response_model=AdministratorReceipt, status_code=201
)
async def invite(
    tenant_id: uuid.UUID,
    body: AdministratorInvite,
    request: Request,
    key: str = Header(alias="Idempotency-Key"),
    current: Actor = Depends(fresh_platform_actor),
) -> AdministratorReceipt:
    return await command(request, current, tenant_id, body, key)


@router.post(
    "/tenants/{tenant_id}/administrators/{user_id}/commands", response_model=AdministratorReceipt
)
async def change(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: AdministratorCommand,
    request: Request,
    key: str = Header(alias="Idempotency-Key"),
    current: Actor = Depends(fresh_platform_actor),
) -> AdministratorReceipt:
    return await command(request, current, tenant_id, body, key, user_id)


@router.post(
    "/tenants/{tenant_id}/administrators/{user_id}/password-recovery",
    response_model=AdministratorRecoveryLink,
)
async def password_recovery(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: AdministratorRecoveryRequest,
    request: Request,
    response: Response,
    current: Actor = Depends(fresh_platform_actor),
) -> AdministratorRecoveryLink:
    # Intentionally keyless: a secret cannot enter an idempotency receipt. The UI
    # never automatically replays this provider call, including after token refresh.
    if "idempotency-key" in request.headers:
        raise ValidationFailedError("password recovery requests must not use automatic replay")
    async with request.app.state.session_factory() as db, db.begin():
        await authorize(db, request, current, write=True)
        role = await access.administrator_role(db)
        with tenant_scope(tenant_id):
            tenant = await access.target_tenant(db, tenant_id, current, write=True)
            user, assignment = await access.administrator(db, tenant_id, role.id, user_id)
            if (
                user.updated_at != body.expected_updated_at
                or assignment.updated_at != body.expected_assignment_updated_at
            ):
                raise ConflictError(
                    "administrator changed; refresh and review before resetting the password"
                )
            today = utcnow().date()
            if (
                tenant.status != "active"
                or user.status != "active"
                or not assignment.is_active
                or assignment.valid_from > today
                or (assignment.valid_to and assignment.valid_to < today)
                or not user.authentik_sub
            ):
                raise ConflictError(
                    "only an active, accepted tenant administrator can reset a password"
                )
            subject = user.authentik_sub
            if not recovery_supported(request.app.state.settings, subject):
                raise ConflictError(
                    "this sign-in provider does not support billing password recovery"
                )
            provider = recovery_directory(request)
            expected_email = user.email
            record(
                db,
                Actor(tenant_id, current.user_id),
                action="user.password_recovery_requested",
                entity="user",
                entity_id=user_id,
                reason=body.reason,
            )
        with tenant_scope(current.tenant_id):
            record(
                db,
                current,
                action="platform.tenant_administrator_password_recovery_requested",
                entity="tenant",
                entity_id=tenant_id,
                reason=body.reason,
                changes={
                    "administrator_id": str(user_id),
                    "assignment_id": str(assignment.id),
                    "delivery": body.delivery,
                },
            )
    # Commit the audited intent before the external operation; release database locks.
    link, expires = await provider.recover(subject, body.delivery, expected_email)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return AdministratorRecoveryLink(
        delivery=body.delivery,
        tenant_id=tenant_id,
        administrator_id=user_id,
        recovery_url=link,
        expires_at=expires,
    )
