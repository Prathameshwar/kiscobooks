from __future__ import annotations

import time
import uuid
from typing import cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.test_gap_login import bearer, seed_login


async def test_verified_self_link_audit_duplicate_rollback_and_ownership(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    uid = await seed_login(factory, tenant_a, tenant_b)
    key = RSAKey.generate_key(2048, {"kid": "web"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        cast(FastAPI, app).state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        path = f"/v1/users/{uid}/identities"
        headers = bearer(
            key,
            auth_time=int(time.time()),
            linked_identities=[{"provider": "google", "subject": "owned-google"}],
        )
        body = {"provider": "google", "provider_sub": "owned-google"}
        assert (await client.post(path, headers=bearer(key), json=body)).status_code == 403
        assert (
            await client.post(path, headers=headers, json={**body, "provider_sub": "someone-else"})
        ).status_code == 403
        created = await client.post(path, headers=headers, json=body)
        assert created.status_code == 201, created.text
        assert (await client.post(path, headers=headers, json=body)).status_code == 409
        with tenant_scope(tenant_a):
            async with factory() as db:
                rows = list(
                    await db.scalars(
                        select(Outbox).where(Outbox.event_type == "user.identity_linked")
                    )
                )
                assert len(rows) == 1 and "owned-google" not in str(rows[0].payload)
        primary = await client.post(
            path, headers=headers, json={"provider": "authentik", "provider_sub": "person"}
        )
        assert primary.status_code == 201
        assert (
            await client.delete(path + "/" + primary.json()["id"], headers=headers)
        ).status_code == 409
        assert (
            await client.delete(path + "/" + created.json()["id"], headers=headers)
        ).status_code == 204
