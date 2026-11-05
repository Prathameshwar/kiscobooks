"""Read-only support authority is derived from a live, attributable session on every request."""

from __future__ import annotations

import uuid
from dataclasses import replace

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.domain.impersonation import assert_session_usable
from identity.models import ImpersonationSession, Tenant, User
from identity.services.login import live_grants


async def apply_impersonation(request: Request, original: Actor) -> Actor:
    if request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions allow read requests only")
    original.require_scope("user.impersonate", target=ScopePath())
    claims = request.state.verified_claims
    if request.app.state.settings.platform_operators.get(claims.sub) != original.user_id:
        raise PermissionDeniedError("support requires a configured platform operator")
    try:
        session_id = uuid.UUID(request.headers["x-impersonation-session"])
    except ValueError as exc:
        raise PermissionDeniedError("invalid support session") from exc
    async with request.app.state.session_factory() as db:
        # Opaque session reference plus its verified initiating actor locates one target tenant.
        with unfiltered():
            tenant_id = await db.scalar(
                select(ImpersonationSession.tenant_id).where(
                    ImpersonationSession.id == session_id,
                    ImpersonationSession.actor_user_id == original.user_id,
                )
            )
        if tenant_id is None:
            raise PermissionDeniedError("support session is unavailable")
    request.state.original_actor = original
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            row = await db.get(ImpersonationSession, session_id)
            if row is None:
                raise PermissionDeniedError("support session is unavailable")
            effective = Actor(
                tenant_id,
                row.target_user_id,
                real_user_id=original.user_id,
                real_tenant_id=original.tenant_id,
                impersonation_id=session_id,
                impersonation_expires_at=int(row.expires_at.timestamp()),
            )
            await refresh_impersonation(db, request, effective)
    return effective


async def refresh_impersonation(db: AsyncSession, request: Request, current: Actor) -> None:
    row = await db.get(ImpersonationSession, current.impersonation_id)
    if (
        row is None
        or row.actor_user_id != current.real_user_id
        or row.target_user_id != current.user_id
    ):
        raise PermissionDeniedError("support session is unavailable")
    assert_session_usable(ended_at=row.ended_at, expires_at=row.expires_at, now=utcnow())
    target = await db.get(User, current.user_id)
    tenant = await db.get(Tenant, current.tenant_id)
    if target is None or target.status != "active" or tenant is None or tenant.status != "active":
        raise PermissionDeniedError("support target is unavailable")
    # The initiating actor was freshly authenticated in its own tenant before this lookup.
    grants, groups = await live_grants(db, current.user_id)
    current.grants = tuple(
        replace(
            g,
            permissions=frozenset(
                p for p in g.permissions if p.endswith(".read") and not p.startswith("platform.")
            ),
        )
        for g in grants
    )
    current.group_ids = groups
