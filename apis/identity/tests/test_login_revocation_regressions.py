from __future__ import annotations

import datetime as dt
import time
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import RoleAssignment, User
from tests.factories import build_role_assignment, build_role_permission, build_user
from tests.test_gap_login import bearer, seed_login


@pytest.mark.parametrize("auth_time", [None, "old", "fresh"])
@pytest.mark.parametrize("administrative", [False, True])
async def test_revocation_requires_new_provider_authentication(
    app: FastAPI,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    auth_time: str | None,
    administrative: bool,
) -> None:
    user_id = await seed_login(factory, tenant_a, tenant_b)
    if administrative:
        with tenant_scope(tenant_a):
            async with factory() as db, db.begin():
                assignment = (await db.scalars(select(RoleAssignment))).one()
                admin = build_user(
                    tenant_id=tenant_a, authentik_sub="administrator", email="admin@example.test"
                )
                db.add(admin)
                db.add(
                    build_role_permission(
                        tenant_id=tenant_a, role_id=assignment.role_id, permission_key="user.update"
                    )
                )
                await db.flush()
                db.add(
                    build_role_assignment(
                        tenant_id=tenant_a,
                        subject_id=admin.id,
                        role_id=assignment.role_id,
                        valid_from=utcnow().date() - dt.timedelta(days=1),
                    )
                )
    key = RSAKey.generate_key(2048, {"kid": "web"})
    now = int(time.time())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        app.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        original = bearer(key, auth_time=now - 120)
        assert (await client.get("/v1/session", headers=original)).status_code == 200
        if administrative:
            revoked = await client.post(
                f"/v1/users/{user_id}/revoke-sessions",
                headers=bearer(key, subject="administrator", auth_time=now),
                json={"reason": "lost device"},
            )
        else:
            revoked = await client.post("/v1/session/revoke", headers=original)
        assert revoked.status_code == 204, revoked.text
        assert (await client.get("/v1/session", headers=original)).status_code == 401
        # Set a past cutoff in the disposable DB, avoiding sleep/clock-dependent re-login tests.
        with tenant_scope(tenant_a):
            async with factory() as db, db.begin():
                user = await db.get(User, user_id)
                assert user is not None
                user.tokens_valid_after_at = utcnow() - dt.timedelta(seconds=30)
        claims = (
            {} if auth_time is None else {"auth_time": now - 120 if auth_time == "old" else now}
        )
        renewed = bearer(key, iat=now, exp=now + 300, **claims)
        response = await client.get("/v1/session", headers=renewed)
        assert response.status_code == (200 if auth_time == "fresh" else 401)
