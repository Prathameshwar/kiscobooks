"""Authorized invitation management and verified single-use acceptance."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, PermissionDeniedError
from billing_platform.outbox import emit
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor, refresh_current, verified_claims
from identity.api.dependencies import session
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import Tenant, User, UserInvitation
from identity.schemas.base import Page, StrictModel
from identity.schemas.login import ReasonRequest
from identity.schemas.user import UserDetail
from identity.services.invitations import issue_invitation

router = APIRouter(prefix="/v1", responses=ERROR_RESPONSES, route_class=StrictRoute)


class InvitationItem(StrictModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    expires_at: dt.datetime
    accepted_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    created_at: dt.datetime


@router.post("/users/{user_id}/invitations", response_model=InvitationItem, status_code=201)
async def resend_invitation(
    user_id: uuid.UUID,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current: Actor = Depends(actor),
) -> InvitationItem:
    from typing import Any

    from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent

    async def authorize(db: AsyncSession, references: dict[str, Any] | None) -> None:
        await lock_tenant(db, current.tenant_id)
        await refresh_current(db, request, current)
        current.require_scope("user.invite", target=ScopePath())
        if await db.get(User, user_id) is None:
            raise NotFoundError("user not found")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        user = await db.get(User, user_id)
        assert user is not None
        row = await issue_invitation(db, current, user, request.app.state.settings)
        return CommandReceipt(201, {"invitation_id": str(row.id)})

    async def render(db: AsyncSession, references: dict[str, Any]) -> InvitationItem:
        row = await db.get(UserInvitation, uuid.UUID(references["invitation_id"]))
        if row is None:
            raise NotFoundError("invitation not found")
        return InvitationItem.model_validate(row)

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            tenant_id=current.tenant_id,
            company_id=None,
            actor_id=current.user_id,
            operation="identity.invitation.resend",
            key=idempotency_key,
            request={"user_id": str(user_id)},
        ),
        authorize=authorize,
        mutate=mutate,
        render=render,
    )
    return result.value


@router.get("/users/{user_id}/invitations", response_model=Page[InvitationItem])
async def list_invitations(
    user_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[InvitationItem]:
    current.require_scope("user.read", target=ScopePath())
    if await db.get(User, user_id) is None:
        raise NotFoundError("user not found")
    return await paged(
        db,
        request,
        select(UserInvitation).where(UserInvitation.user_id == user_id),
        model=UserInvitation,
        schema=InvitationItem,
        limit=limit,
        cursor=cursor,
    )


@router.post("/invitations/{invitation_id}/cancel", response_model=InvitationItem)
async def cancel_invitation(
    invitation_id: uuid.UUID,
    body: ReasonRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserInvitation:
    current.require_scope("user.invite", target=ScopePath())
    row = await db.get(UserInvitation, invitation_id)
    if row is None:
        raise NotFoundError("invitation not found")
    if row.status == "accepted":
        raise ConflictError("invitation was already accepted")
    if row.status != "cancelled":
        row.status, row.cancelled_at, row.updated_by = "cancelled", utcnow(), current.user_id
        emit(
            db,
            tenant_id=current.tenant_id,
            aggregate_type="user_invitation",
            aggregate_id=row.id,
            event_type="user.invitation_cancelled",
            payload=audit_payload(
                action="user.invitation_cancelled",
                category="security",
                entity_type="user_invitation",
                entity_id=row.id,
                actor_user_id=current.user_id,
                reason=body.reason,
            ),
        )
    await db.flush()
    return row


@router.post("/tenants/{tenant_id}/invitations/{invitation_id}/accept", response_model=UserDetail)
async def accept_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
) -> UserDetail:
    # Authenticated through provider proof; the user has no local permissions until activation.
    claims = await verified_claims(request, authorization)
    if (
        not claims.email_verified
        or not claims.email
        or (claims.org_id and claims.org_id != tenant_id)
    ):
        raise PermissionDeniedError("verified invitation ownership is required")
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            db.sync_session.info[CAPTURE_KEY] = True
            await lock_tenant(db, tenant_id)
            row = await db.get(UserInvitation, invitation_id)
            tenant = await db.get(Tenant, tenant_id)
            if row is None:
                raise NotFoundError("invitation not found")
            user = await db.get(User, row.user_id)
            if (
                user is None
                or user.email.casefold() != claims.email.casefold()
                or tenant is None
                or tenant.status != "active"
            ):
                raise PermissionDeniedError("verified invitation ownership is required")
            if row.status != "pending" or row.expires_at <= utcnow() or user.status != "invited":
                raise ConflictError("invitation is no longer available")
            user.authentik_sub = claims.sub
            user.status = "active"
            user.updated_by = user.id
            user.email_verified_at = user.activated_at = utcnow()
            row.status, row.accepted_at, row.updated_by = "accepted", utcnow(), user.id
            emit(
                db,
                tenant_id=tenant_id,
                aggregate_type="user",
                aggregate_id=user.id,
                event_type="user.activated",
                payload=audit_payload(
                    action="user.activated",
                    category="security",
                    entity_type="user",
                    entity_id=user.id,
                    actor_user_id=user.id,
                ),
            )
            await db.flush()
            return UserDetail.model_validate(user)
