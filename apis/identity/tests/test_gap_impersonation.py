from __future__ import annotations

import datetime as dt
import time
import uuid
from typing import cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.gateway import decode_actor_context
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import ImpersonationSession, RoleAssignment
from tests.api_support import ACTOR_SECRET
from tests.factories import (
    build_company,
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
)
from tests.test_gap_login import bearer, seed_login


async def test_support_is_read_only_attributed_scoped_and_ends_immediately(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    operator = await seed_login(factory, tenant_a, tenant_b)
    async with factory() as db, db.begin():
        with tenant_scope(tenant_a):
            assignment = (await db.scalars(select(RoleAssignment))).one()
            db.add(
                build_role_permission(
                    tenant_id=tenant_a,
                    role_id=assignment.role_id,
                    permission_key="user.impersonate",
                )
            )
            await db.flush()
        with tenant_scope(tenant_b):
            target = build_user(tenant_id=tenant_b, email="target@other.example")
            company = build_company(tenant_id=tenant_b)
            role = build_role(tenant_id=tenant_b)
            db.add_all([target, company, role])
            await db.flush()
            for permission in ["company.read", "company.update", "user.read"]:
                db.add(
                    build_role_permission(
                        tenant_id=tenant_b, role_id=role.id, permission_key=permission
                    )
                )
            db.add(build_role_assignment(tenant_id=tenant_b, role_id=role.id, subject_id=target.id))
            tid, cid = target.id, company.id
            await db.flush()
    key = RSAKey.generate_key(2048, {"kid": "web"})
    application = cast(FastAPI, app)
    application.state.settings.platform_operators = {"person": operator}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        application.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        headers = bearer(key, auth_time=int(time.time()))
        root = f"/v1/platform/tenants/{tenant_b}/impersonation-sessions"
        started = await client.post(
            root, headers=headers, json={"target_user_id": str(tid), "reason": "investigate ticket"}
        )
        assert started.status_code == 201, started.text
        sid = started.json()["id"]
        support = {**headers, "X-Impersonation-Session": sid}
        assert (await client.get(f"/v1/companies/{cid}", headers=support)).status_code == 200
        assert (
            await client.patch(
                f"/v1/companies/{cid}", headers=support, json={"display_name": "Changed"}
            )
        ).status_code == 403
        # A sensitive GET emits both identities through the shared audit context.
        read = await client.get(f"/v1/companies/{cid}/tax-registrations", headers=support)
        assert read.status_code == 200, read.text
        gateway = await client.get("/internal/v1/gateway/authorize", headers=support)
        assert gateway.status_code == 204, gateway.text
        decoded = decode_actor_context(
            gateway.headers["x-actor-context"],
            gateway.headers["x-actor-signature"],
            ACTOR_SECRET.encode(),
        )
        assert decoded.user_id == tid and decoded.real_user_id == operator
        assert "company.update" not in decoded.permissions
        async with factory() as db:
            with tenant_scope(tenant_b):
                event = (
                    await db.scalars(
                        select(Outbox).where(Outbox.event_type == "company.tax_registrations_read")
                    )
                ).one()
                assert event.payload["actor_user_id"] == str(operator)
                assert event.payload["on_behalf_of_user_id"] == str(tid)
        assert (await client.post(root + f"/{sid}/end", headers=headers)).status_code == 200
        assert (await client.get(f"/v1/companies/{cid}", headers=support)).status_code == 403
        restarted = await client.post(
            root, headers=headers, json={"target_user_id": str(tid), "reason": "follow-up"}
        )
        sid2 = restarted.json()["id"]
        async with factory() as db, db.begin():
            with tenant_scope(tenant_b):
                row = await db.get(ImpersonationSession, uuid.UUID(sid2))
                assert row is not None
                row.expires_at = utcnow() - dt.timedelta(seconds=1)
        assert (
            await client.get(
                f"/v1/companies/{cid}", headers={**headers, "X-Impersonation-Session": sid2}
            )
        ).status_code == 403
