"""Audited support session start/end, with expiry enforced independently of cleanup."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, PermissionDeniedError
from billing_platform.ids import uuid7
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select

from identity.api.auth import Actor, refresh_current
from identity.api.platform import platform_actor
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.models import ImpersonationSession, Tenant, User
from identity.schemas.base import StrictModel
from identity.schemas.login import ReasonRequest
from identity.services.audit import record

router = APIRouter(
    prefix="/v1/platform/tenants/{tenant_id}/impersonation-sessions",
    route_class=StrictRoute,
    responses=ERROR_RESPONSES,
)


class SupportStart(ReasonRequest):
    target_user_id: uuid.UUID
    ticket_reference: str | None = Field(default=None, max_length=120)
    minutes: int = Field(default=15, ge=1, le=30, strict=True)


class SupportSession(StrictModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    target_user_id: uuid.UUID
    started_at: dt.datetime
    expires_at: dt.datetime
    ended_at: dt.datetime | None
    ended_reason: str | None
    reason: str


@router.post("", response_model=SupportSession, status_code=201)
async def start(
    tenant_id: uuid.UUID,
    body: SupportStart,
    request: Request,
    current: Actor = Depends(platform_actor),
) -> SupportSession:
    current.require_scope("user.impersonate", target=ScopePath())
    if current.user_id == body.target_user_id or current.impersonation_id is not None:
        raise PermissionDeniedError("self and nested support sessions are forbidden")
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await refresh_current(db, request, current)
            current.require_scope("user.impersonate", target=ScopePath())
            with tenant_scope(tenant_id):
                await lock_tenant(db, tenant_id)
                target = await db.get(User, body.target_user_id)
                tenant = await db.get(Tenant, tenant_id)
                if (
                    target is None
                    or target.status != "active"
                    or tenant is None
                    or tenant.status != "active"
                ):
                    raise NotFoundError("active support target not found")
                # One active session per operator/target; retries return the same bounded session.
                row = await db.scalar(
                    select(ImpersonationSession)
                    .where(
                        ImpersonationSession.actor_user_id == current.user_id,
                        ImpersonationSession.target_user_id == body.target_user_id,
                        ImpersonationSession.ended_at.is_(None),
                        ImpersonationSession.expires_at > utcnow(),
                    )
                    .limit(1)
                )
                if row is None:
                    now = utcnow()
                    row = ImpersonationSession(
                        id=uuid7(),
                        tenant_id=tenant_id,
                        actor_user_id=current.user_id,
                        target_user_id=target.id,
                        reason=body.reason,
                        ticket_reference=body.ticket_reference,
                        started_at=now,
                        expires_at=now + dt.timedelta(minutes=body.minutes),
                        created_by=current.user_id,
                        updated_by=current.user_id,
                    )
                    db.add(row)
                    record(
                        db,
                        Actor(tenant_id, current.user_id),
                        action="user.impersonation_started",
                        entity="impersonation_session",
                        entity_id=row.id,
                        reason=body.reason,
                        changes={"user_id": {"to": str(target.id)}},
                    )
                await db.flush()
                return SupportSession.model_validate(row)


@router.post("/{session_id}/end", response_model=SupportSession)
async def end(
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(platform_actor),
) -> SupportSession:
    current.require_scope("user.impersonate", target=ScopePath())
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, tenant_id)
            row = await db.get(ImpersonationSession, session_id)
            if row is None:
                raise NotFoundError("support session not found")
            if row.actor_user_id != current.user_id:
                raise PermissionDeniedError("only the initiating operator may end this session")
            if row.ended_at is None:
                row.ended_at, row.ended_reason, row.updated_by = utcnow(), "manual", current.user_id
                record(
                    db,
                    Actor(tenant_id, current.user_id),
                    action="user.impersonation_ended",
                    entity="impersonation_session",
                    entity_id=row.id,
                    changes={"user_id": {"to": str(row.target_user_id)}},
                )
            await db.flush()
            return SupportSession.model_validate(row)
