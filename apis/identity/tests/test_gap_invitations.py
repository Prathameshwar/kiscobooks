from __future__ import annotations

import uuid
from typing import cast

import httpx
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import UserInvitation
from tests.api_support import actor_headers, grant
from tests.factories import seed_two_tenants
from tests.test_gap_login import bearer


async def test_invitation_requires_verified_owner_and_accepts_once(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    async with factory() as db:
        await seed_two_tenants(db, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["user.invite", "user.read"])]
    )
    created = await client.post(
        "/v1/users",
        headers=headers,
        json={"email": "invited@example.test", "first_name": "Invited"},
    )
    assert created.status_code == 201, created.text
    listing = await client.get(f"/v1/users/{created.json()['id']}/invitations", headers=headers)
    invitation_id = listing.json()["items"][0]["id"]
    key = RSAKey.generate_key(2048, {"kid": "web"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}),
        )
    ) as provider:
        cast(FastAPI, app).state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"),
            provider,
        )
        route = f"/v1/tenants/{tenant_a}/invitations/{invitation_id}/accept"
        assert (await client.post(route)).status_code == 401
        for email, verified in (("other@example.test", True), ("invited@example.test", False)):
            assert (
                await client.post(route, headers=bearer(key, email=email, email_verified=verified))
            ).status_code == 403
        proof = bearer(key, email="invited@example.test", email_verified=True)
        accepted = await client.post(route, headers=proof)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "active"
        assert (await client.post(route, headers=proof)).status_code == 409
        session = await client.get("/v1/session", headers=proof)
        assert session.status_code == 200 and session.json()["permissions"] == []
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert not list(await db.scalars(select(UserInvitation)))


async def test_resend_cancels_previous_invitation_and_cancel_is_repeatable(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    async with factory() as db:
        await seed_two_tenants(db, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["user.invite", "user.read"])]
    )
    created = await client.post(
        "/v1/users", headers=headers, json={"email": "new@example.test", "first_name": "New"}
    )
    user_id = created.json()["id"]
    resend_headers = {**headers, "Idempotency-Key": "resend-invitation-1"}
    resent = await client.post(f"/v1/users/{user_id}/invitations", headers=resend_headers)
    repeated = await client.post(f"/v1/users/{user_id}/invitations", headers=resend_headers)
    assert repeated.json() == resent.json()
    assert resent.status_code == 201, resent.text
    listing = await client.get(f"/v1/users/{user_id}/invitations", headers=headers)
    assert sorted(row["status"] for row in listing.json()["items"]) == ["cancelled", "pending"]
    for _ in range(2):
        cancelled = await client.post(
            f"/v1/invitations/{resent.json()['id']}/cancel",
            headers=headers,
            json={"reason": "Invitation withdrawn"},
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
