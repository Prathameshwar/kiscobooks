from __future__ import annotations

import json
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

from identity.models import RoleAssignment
from tests.factories import build_company, build_role_permission
from tests.test_gap_login import bearer, seed_login


class MemoryProofs:
    """Unit-test adapter only; never configured by production application code."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def put(self, key: str, value: str, seconds: int) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def take(self, key: str) -> str | None:
        return self.values.pop(key, None)


async def test_company_proof_is_fresh_scoped_single_use_and_requires_committed_audit(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_login(factory, tenant_a, tenant_b)
    async with factory() as db, db.begin():
        with tenant_scope(tenant_a):
            company = build_company(tenant_id=tenant_a, requires_step_up=True)
            db.add(company)
            assignment = (await db.scalars(select(RoleAssignment))).one()
            db.add(
                build_role_permission(
                    tenant_id=tenant_a, role_id=assignment.role_id, permission_key="company.read"
                )
            )
            cid = company.id
    application = cast(FastAPI, app)
    memory = MemoryProofs()
    application.state.proof_store = memory
    key = RSAKey.generate_key(2048, {"kid": "web"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        application.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        headers = bearer(key, auth_time=int(time.time()) - 10)
        url = f"/v1/companies/{cid}"
        assert (await client.get(url, headers=headers)).status_code == 403
        challenge = await client.post(url + "/step-up/challenge", headers=headers)
        assert challenge.status_code == 200, challenge.text
        body = {"challenge_id": challenge.json()["challenge_id"]}
        assert (
            await client.post(url + "/step-up/complete", headers=headers, json=body)
        ).status_code == 403
        # Move only the test challenge clock, retaining a real signed provider token.
        challenge_key = next(k for k in memory.values if ":challenge:" in k)
        value = json.loads(memory.values[challenge_key])
        value["created_at"] -= 2
        memory.values[challenge_key] = json.dumps(value)
        fresh = bearer(key, auth_time=int(time.time()))
        completed = await client.post(url + "/step-up/complete", headers=fresh, json=body)
        assert completed.status_code == 200, completed.text
        proof = completed.json()["proof"]
        assert (
            await client.post(url + "/step-up/complete", headers=fresh, json=body)
        ).status_code == 403
        proven = {**fresh, "X-Company-Step-Up": proof}
        assert (await client.get(url, headers=proven)).status_code == 200
        # Console bootstrap must select the company and forward that company's proof.
        assert (await client.get("/v1/session", headers=fresh)).json()["company"] is None
        selected = await client.get(f"/v1/session?company_id={cid}", headers=proven)
        assert selected.status_code == 200
        assert selected.json()["company"]["id"] == str(cid)
        assert (await client.get(f"/v1/session?company_id={cid}", headers=fresh)).status_code == 403
        proof_key = next(k for k in memory.values if ":proof:" in k)
        value = json.loads(memory.values[proof_key])
        value["receipt_id"] = str(uuid.uuid4())
        memory.values[proof_key] = json.dumps(value)
        assert (await client.get(url, headers=proven)).status_code == 403


async def test_company_selection_requires_step_up(
    app: FastAPI,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_login(factory, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            company = build_company(tenant_id=tenant_a, requires_step_up=True)
            db.add(company)
            assignment = (await db.scalars(select(RoleAssignment))).one()
            db.add(
                build_role_permission(
                    tenant_id=tenant_a, role_id=assignment.role_id, permission_key="company.read"
                )
            )
            cid = company.id
    key = RSAKey.generate_key(2048, {"kid": "web"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        app.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        result = await client.get(f"/v1/session?company_id={cid}", headers=bearer(key))
        assert result.status_code == 403
        assert result.json()["error"]["code"] == "step_up_required"
