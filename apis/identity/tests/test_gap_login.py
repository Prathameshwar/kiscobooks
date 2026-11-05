from __future__ import annotations

import datetime as dt
import time
import uuid
from typing import cast

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import RoleAssignment, User
from tests.api_support import actor_headers
from tests.factories import (
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    seed_two_tenants,
)


@pytest.fixture(scope="module")
def key() -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": "web"})


def bearer(key: RSAKey, subject: str = "person", **claims: object) -> dict[str, str]:
    now = int(time.time())
    return {
        "Authorization": "Bearer "
        + jwt.encode(
            {"alg": "RS256", "kid": "web"},
            {
                "iss": "https://id.test/",
                "aud": "web",
                "sub": subject,
                "iat": now,
                "exp": now + 300,
                "scope": "billing.api",
                **claims,
            },
            key,
        )
    }


async def seed_login(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> uuid.UUID:
    async with factory() as db:
        await seed_two_tenants(db, tenant_a, tenant_b)
        with tenant_scope(tenant_a):
            user = build_user(tenant_id=tenant_a, authentik_sub="person")
            role = build_role(tenant_id=tenant_a)
            db.add_all([user, role])
            await db.flush()
            db.add(
                build_role_permission(
                    tenant_id=tenant_a, role_id=role.id, permission_key="user.read"
                )
            )
            db.add(
                build_role_assignment(
                    tenant_id=tenant_a,
                    subject_id=user.id,
                    role_id=role.id,
                    valid_from=utcnow().date() - dt.timedelta(days=1),
                )
            )
            await db.commit()
            return user.id


async def test_bearer_session_uses_live_grants_and_revocation(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    key: RSAKey,
) -> None:
    user_id = await seed_login(factory, tenant_a, tenant_b)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}),
        )
    ) as provider:
        cast(FastAPI, app).state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"),
            provider,
        )
        headers = bearer(key)
        response = await client.get("/v1/session", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["user"]["id"] == str(user_id)
        assert response.json()["permissions"] == ["user.read"]
        assert (await client.get("/v1/users", headers=headers)).status_code == 200
        async with factory() as db, db.begin():
            with tenant_scope(tenant_a):
                assignment = (await db.scalars(select(RoleAssignment))).one()
                assignment.is_active = False
        assert (await client.get("/v1/users", headers=headers)).status_code == 403
        response = await client.patch(
            "/v1/session/preferences", headers=headers, json={"theme": "dark"}
        )
        assert response.status_code == 200 and response.json()["theme"] == "dark"
        assert (await client.post("/v1/session/revoke", headers=headers)).status_code == 204
        assert (await client.get("/v1/session", headers=headers)).status_code == 401


async def test_wrong_tenant_and_signed_fixture_context_cannot_authenticate_oidc(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    key: RSAKey,
) -> None:
    user_id = await seed_login(factory, tenant_a, tenant_b)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}),
        )
    ) as provider:
        cast(FastAPI, app).state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"),
            provider,
        )
        assert (
            await client.get("/v1/session", headers=bearer(key, org_id=str(tenant_b)))
        ).status_code == 401
        assert (
            await client.get(
                "/v1/session", headers=actor_headers(tenant_id=tenant_a, user_id=user_id)
            )
        ).status_code == 401
        async with factory() as db, db.begin():
            with tenant_scope(tenant_a):
                user = await db.get(User, user_id)
                assert user is not None
                user.status = "suspended"
        assert (await client.get("/v1/session", headers=bearer(key))).status_code == 401
