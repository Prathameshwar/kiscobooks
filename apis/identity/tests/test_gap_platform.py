from __future__ import annotations

import hashlib
import time
import uuid
from typing import cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import RoleAssignment, User
from identity.seeds.regional import seed_regional_defaults
from tests.factories import build_role_permission, seed_system_role
from tests.test_gap_login import bearer, seed_login


async def test_platform_bootstrap_replay_and_tenant_boundary(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    monkeypatch,
) -> None:
    from identity.services.administrator_provider import AdministratorProvider

    monkeypatch.setattr(AdministratorProvider, "__init__", lambda self, settings, http: None)

    async def create(self, *, email, name, password, marker):
        return "bill-admin-" + marker.hex, hashlib.sha256(marker.bytes).hexdigest()

    monkeypatch.setattr(AdministratorProvider, "create", create)

    async def activate(self, *, email, marker, subject):
        return None

    monkeypatch.setattr(AdministratorProvider, "activate", activate)
    uid = await seed_login(factory, tenant_a, tenant_b)
    async with factory() as db:
        await seed_regional_defaults(db)
        await seed_system_role(db, "tenant_admin")
        with tenant_scope(tenant_a):
            assignment = (await db.scalars(select(RoleAssignment))).one()
            for permission in [
                "platform.tenant.create",
                "platform.tenant.read",
                "platform.tenant.suspend",
            ]:
                db.add(
                    build_role_permission(
                        tenant_id=tenant_a, role_id=assignment.role_id, permission_key=permission
                    )
                )
            await db.commit()
    key = RSAKey.generate_key(2048, {"kid": "web"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        application = cast(FastAPI, app)
        application.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        headers = {**bearer(key, auth_time=int(time.time())), "Idempotency-Key": "provision-1"}
        body = {
            "name": "New organization",
            "administrator_email": "admin@new.example",
            "administrator_name": "Initial admin",
            "country_code": "IN",
            "currency_code": "INR",
            "administrator_password": "temporary-secret-for-test",
            "recipient_confirmed": True,
        }
        assert (
            await client.post("/v1/platform/tenants", headers=headers, json=body)
        ).status_code == 403
        application.state.settings.platform_operators = {"person": uid}
        response = await client.post("/v1/platform/tenants", headers=headers, json=body)
        assert response.status_code == 201, response.text
        tid = response.json()["id"]
        replay = await client.post("/v1/platform/tenants", headers=headers, json=body)
        assert replay.status_code == 201 and replay.json()["id"] == tid
        assert (
            await client.post(
                "/v1/platform/tenants", headers=headers, json={**body, "name": "Changed"}
            )
        ).status_code == 422
        listing = await client.get("/v1/platform/tenants", headers=headers)
        assert listing.status_code == 200, listing.text
        assert tid in [row["id"] for row in listing.json()["items"]]
        # Ordinary self-service paths cannot cross to a provisioned tenant.
        assert (await client.get(f"/v1/tenants/{tid}", headers=headers)).status_code in {403, 404}
        for state in ["suspended", "active"]:
            detail = (await client.get(f"/v1/platform/tenants/{tid}", headers=headers)).json()
            response = await client.post(
                f"/v1/platform/tenants/{tid}/lifecycle",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "status": state,
                    "reason": "maintenance",
                    "expected_updated_at": detail["updated_at"],
                },
            )
            assert response.status_code == 200, response.text
        async with factory() as db:
            with tenant_scope(uuid.UUID(tid)):
                users = list(await db.scalars(select(User)))
                grants = list(await db.scalars(select(RoleAssignment)))
                assert len(users) == len(grants) == 1 and users[0].status == "active"
