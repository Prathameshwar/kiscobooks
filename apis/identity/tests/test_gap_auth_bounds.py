from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.ids import uuid7
from fastapi import Request

from identity.api.auth import Actor
from identity.models import Company, Department, ImpersonationSession, Tenant, User, UserApiToken
from identity.services import tokens
from identity.services.impersonation import refresh_impersonation
from identity.services.login import live_grants


def context():
    current = Actor(uuid7(), uuid7())
    token = SimpleNamespace(
        user_id=current.user_id,
        token_hash="digest",
        revoked_at=None,
        expires_at=utcnow() + dt.timedelta(days=1),
        created_at=utcnow() - dt.timedelta(days=1),
        scopes={"company_id": None, "permissions": ["company.read"]},
    )
    user = SimpleNamespace(id=current.user_id, status="active", tokens_valid_after_at=None)
    tenant = SimpleNamespace(status="active")
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.state.api_token_id, request.state.api_token_digest = uuid7(), "digest"
    return current, token, user, tenant, request


@pytest.mark.parametrize(
    "bad",
    [
        "revoked",
        "expired",
        "user_disabled",
        "tenant_disabled",
        "revocation_time",
        "scope_type",
        "scope_keys",
        "scope_permissions",
        "scope_nested",
        "company_uuid",
        "company_missing",
    ],
)
async def test_bad_tokens_fail_closed(bad):
    current, token, user, tenant, request = context()
    if bad == "revoked":
        token.revoked_at = utcnow()
    if bad == "expired":
        token.expires_at = utcnow() - dt.timedelta(seconds=1)
    if bad == "user_disabled":
        user.status = "suspended"
    if bad == "tenant_disabled":
        tenant.status = "suspended"
    if bad == "revocation_time":
        user.tokens_valid_after_at = utcnow()
    if bad == "scope_type":
        token.scopes = None
    if bad == "scope_keys":
        token.scopes = {}
    if bad == "scope_permissions":
        token.scopes["permissions"] = "company.read"
    if bad == "scope_nested":
        token.scopes["permissions"] = [{}]
    if bad == "company_uuid":
        token.scopes["company_id"] = "invalid"
    if bad == "company_missing":
        token.scopes["company_id"] = str(uuid7())
    db = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda model, _: {UserApiToken: token, User: user, Tenant: tenant}.get(
                model
            )
        )
    )
    with pytest.raises(AuthenticationRequiredError):
        await tokens.refresh_token(db, request, current)


async def test_token_authority_intersects_live_grants_and_department_owner(monkeypatch):
    current, token, user, tenant, request = context()
    company, other, department, foreign_department = uuid7(), uuid7(), uuid7(), uuid7()
    token.scopes["company_id"] = str(company)
    token.scopes["permissions"] = ["company.read", "role.manage"]

    def get(model, identifier):
        if model is Department:
            return SimpleNamespace(company_id=company if identifier == department else other)
        return {
            UserApiToken: token,
            User: user,
            Tenant: tenant,
            Company: SimpleNamespace(status="active"),
        }.get(model)

    db = SimpleNamespace(get=AsyncMock(side_effect=get))
    grants = tuple(
        Grant(frozenset({"company.read", "role.manage"}), scope, dt.date(2020, 1, 1))
        for scope in (
            Scope("tenant"),
            Scope("company", company),
            Scope("company", other),
            Scope("department", department),
            Scope("department", foreign_department),
        )
    )
    monkeypatch.setattr(tokens, "live_grants", AsyncMock(return_value=(grants, frozenset())))
    await tokens.refresh_token(db, request, current)
    assert len(current.grants) == 3
    assert all(grant.permissions == frozenset({"company.read"}) for grant in current.grants)
    assert current.grants[0].scope == Scope("company", company)
    token.scopes["permissions"] = []
    await tokens.refresh_token(db, request, current)
    assert current.grants == ()


@pytest.mark.parametrize("kind", ["groups", "grants"])
async def test_authority_resolution_never_partially_accepts_oversized_sets(kind):
    answers = (
        [[uuid7() for _ in range(257)]]
        if kind == "groups"
        else [[], [object() for _ in range(257)]]
    )
    db = SimpleNamespace(scalars=AsyncMock(side_effect=answers))
    with pytest.raises(AuthenticationRequiredError):
        await live_grants(db, uuid7())


@pytest.mark.parametrize("kind", ["missing", "actor", "target", "expired", "ended", "inactive"])
async def test_support_sessions_revalidate_current_target_and_initiator(kind):
    current = Actor(uuid7(), uuid7(), real_user_id=uuid7(), impersonation_id=uuid7())
    row = SimpleNamespace(
        actor_user_id=current.real_user_id,
        target_user_id=current.user_id,
        expires_at=utcnow() + dt.timedelta(minutes=1),
        ended_at=None,
    )
    if kind == "missing":
        row = None
    if kind == "actor":
        row.actor_user_id = uuid7()
    if kind == "target":
        row.target_user_id = uuid7()
    if kind == "expired":
        row.expires_at = utcnow() - dt.timedelta(seconds=1)
    if kind == "ended":
        row.ended_at = utcnow()

    def get(model, _):
        return row if model is ImpersonationSession else SimpleNamespace(status="suspended")

    db = SimpleNamespace(get=AsyncMock(side_effect=get))
    with pytest.raises(PermissionDeniedError):
        await refresh_impersonation(db, None, current)
