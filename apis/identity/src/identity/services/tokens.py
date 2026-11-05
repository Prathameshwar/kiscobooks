"""Hash-only API credentials with live owner grants and scope intersection."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import replace

from billing_platform.authz import Grant, Scope
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import Company, Department, Tenant, User, UserApiToken
from identity.services.login import live_grants

# Credential and policy administration stays in interactive, fresh-authenticated flows.
TOKEN_FORBIDDEN = frozenset(
    {
        "role.manage",
        "role.assign",
        "group.manage",
        "field_policy.manage",
        "user.impersonate",
        "user.invite",
        "user.update",
        "user.deactivate",
        "platform.tenant.create",
        "platform.tenant.read",
        "platform.tenant.suspend",
    }
)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def authenticate_token(request: Request, raw: str) -> Actor:
    if len(raw) > 150 or len(raw) < 48:
        raise AuthenticationRequiredError("invalid API token")
    digest = token_hash(raw)
    async with request.app.state.session_factory() as lookup:
        # Only an unguessable credential digest locates the tenant; no external tenant selector.
        with unfiltered():
            identity = (
                await lookup.execute(
                    select(UserApiToken.tenant_id, UserApiToken.user_id, UserApiToken.id).where(
                        UserApiToken.token_hash == digest
                    )
                )
            ).one_or_none()
    if identity is None:
        raise AuthenticationRequiredError("invalid API token")
    tenant_id, user_id, token_id = identity
    request.state.api_token_id = token_id
    request.state.api_token_digest = digest
    current = Actor(tenant_id, user_id)
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            await refresh_token(db, request, current)
    return current


async def refresh_token(db: AsyncSession, request: Request, current: Actor) -> None:
    row = await db.get(UserApiToken, request.state.api_token_id)
    user = await db.get(User, current.user_id)
    tenant = await db.get(Tenant, current.tenant_id)
    now = utcnow()
    if (
        row is None
        or row.user_id != current.user_id
        or not hmac.compare_digest(row.token_hash, request.state.api_token_digest)
        or row.revoked_at is not None
        or row.expires_at is None
        or row.expires_at <= now
        or user is None
        or user.status != "active"
        or tenant is None
        or tenant.status != "active"
        or (user.tokens_valid_after_at is not None and row.created_at <= user.tokens_valid_after_at)
    ):
        raise AuthenticationRequiredError("API token is expired, revoked or unavailable")
    scopes = row.scopes
    if (
        not isinstance(scopes, dict)
        or set(scopes) != {"permissions", "company_id"}
        or not isinstance(scopes["permissions"], list)
    ):
        raise AuthenticationRequiredError("invalid token scope")
    try:
        permissions = frozenset(scopes["permissions"]) - TOKEN_FORBIDDEN
        company_id = uuid.UUID(scopes["company_id"]) if scopes["company_id"] is not None else None
    except (ValueError, TypeError) as exc:
        raise AuthenticationRequiredError("invalid token scope") from exc
    if company_id is not None:
        company = await db.get(Company, company_id)
        if company is None or company.status != "active":
            raise AuthenticationRequiredError("token company is unavailable")
    live, groups = await live_grants(db, user.id)
    narrowed: list[Grant] = []
    for grant in live:
        permission_set = grant.permissions & permissions
        if not permission_set:
            continue
        scope = grant.scope
        if company_id is not None:
            if scope.scope_type == "tenant":
                scope = Scope("company", company_id)
            elif scope.scope_type == "company" and scope.scope_id != company_id:
                continue
            elif scope.scope_type == "department":
                department = await db.get(Department, scope.scope_id)
                if department is None or department.company_id != company_id:
                    continue
        narrowed.append(replace(grant, permissions=permission_set, scope=scope))
    current.grants, current.group_ids = tuple(narrowed), groups
