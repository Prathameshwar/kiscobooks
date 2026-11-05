from __future__ import annotations

import hashlib
import time
import uuid
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import Outbox, PlatformInstallation, RoleAssignment, Tenant, User
from identity.seeds.installation import seed_installation
from identity.seeds.regional import seed_regional_defaults
from identity.seeds.roles import seed_system_roles
from tests.factories import build_country, build_currency
from tests.test_gap_login import bearer

BODY = {
    "platform_name": "JANSO",
    "public_url": "http://localhost:4320",
    "workspace_name": "Platform Administration",
    "workspace_slug": "platform-admin",
    "administrator_name": "First Administrator",
    "country_code": "IN",
    "currency_code": "INR",
    "timezone": "Asia/Kolkata",
}


@pytest.fixture
async def setup_app(app: object, factory: async_sessionmaker[AsyncSession], monkeypatch):
    from identity.services.administrator_provider import AdministratorProvider

    monkeypatch.setattr(AdministratorProvider, "__init__", lambda self, settings, http: None)

    async def create(self, *, email, name, password, marker):
        return "bill-admin-" + marker.hex, hashlib.sha256(marker.bytes).hexdigest()

    monkeypatch.setattr(AdministratorProvider, "create", create)

    async def activate(self, *, email, marker, subject):
        return None

    monkeypatch.setattr(AdministratorProvider, "activate", activate)
    application = cast(FastAPI, app)
    setup_key = SecretStr(__import__("secrets").token_urlsafe(32))
    application.state.settings.setup_key = setup_key
    key = RSAKey.generate_key(2048, {"kid": "web"})
    async with factory() as db, db.begin():
        db.add(build_currency())
        await db.flush()
        db.add(build_country())
        await db.flush()
        await seed_system_roles(db)
        await seed_installation(db)
        await seed_regional_defaults(db)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        application.state.oidc_http = provider
        application.state.redis = AsyncMock()
        application.state.redis.ping.return_value = True
        application.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        yield application, key, {"X-Setup-Key": setup_key.get_secret_value()}


def signed(key: RSAKey, **claims: object) -> dict[str, str]:
    return bearer(
        key, email="admin@example.com", email_verified=True, auth_time=int(time.time()), **claims
    )


async def test_complete_replay_restart_and_isolation(setup_app, client, factory, tenant_b):
    app, key, access = setup_app
    assert (await client.get("/v1/setup/status")).json() == {"available": True, "completed": False}
    checks = await client.get("/v1/setup/checks", headers=access)
    assert checks.status_code == 200 and checks.json()["ready"]
    headers = {**access, **signed(key)}
    response = await client.post("/v1/setup/complete", json=BODY, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (await client.post("/v1/setup/complete", json=BODY, headers=headers)).json() == result
    assert (
        await client.post(
            "/v1/setup/complete", json={**BODY, "platform_name": "changed"}, headers=headers
        )
    ).status_code == 409
    assert (
        await client.post(
            "/v1/setup/complete", json=BODY, headers={**access, **signed(key, subject="other")}
        )
    ).status_code == 409
    assert (await client.get("/v1/setup/status")).json() == {"available": False, "completed": True}
    # Re-running installation defaults must preserve completion and never reopen bootstrap.
    async with factory() as db, db.begin():
        await seed_installation(db)
    assert (await client.get("/v1/setup/status")).json() == {"available": False, "completed": True}
    # No settings mutation: persisted operator works after the environment mapping is cleared.
    app.state.settings.platform_operators = {}
    listing = await client.get("/v1/platform/tenants", headers=signed(key))
    assert listing.status_code == 200, listing.text
    assert result["tenant_id"] in [t["id"] for t in listing.json()["items"]]
    async with factory() as db:
        with tenant_scope(uuid.UUID(result["tenant_id"])):
            users = list(await db.scalars(select(User)))
            assignments = list(await db.scalars(select(RoleAssignment)))
            events = list(await db.scalars(select(Outbox)))
            assert len(users) == len(assignments) == 1
            assert users[0].user_type == "platform_admin"
            assert users[0].authentik_sub == "person"
            assert len(events) >= 4
            assert all("admin@example.com" not in str(e.payload) for e in events)
        with tenant_scope(tenant_b):
            assert list(await db.scalars(select(User))) == []
            assert list(await db.scalars(select(Tenant))) == []


@pytest.mark.parametrize(
    "headers,claims,expected",
    [
        (False, {}, 403),
        (True, None, 401),
        (True, {"auth_time": int(time.time()) - 900}, 401),
        (True, {"email_verified": False}, 403),
        (True, {"org_id": str(uuid7())}, 403),
    ],
)
async def test_bootstrap_denies_missing_authority(
    setup_app, client, factory, headers, claims, expected
):
    _, key, access = setup_app
    credential = {**access} if headers else {}
    if claims is not None:
        credential.update(
            bearer(
                key,
                **{
                    "email": "admin@example.com",
                    "email_verified": True,
                    "auth_time": int(time.time()),
                    **claims,
                },
            )
        )
    response = await client.post("/v1/setup/complete", headers=credential, json=BODY)
    assert response.status_code == expected, response.text
    async with factory() as db:
        with unfiltered():
            assert list(await db.scalars(select(Tenant))) == []
            assert list(await db.scalars(select(Outbox))) == []


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": "Bad/Zone"},
        {"country_code": "XX"},
        {"public_url": "http://evil.example"},
        {"public_url": "https://example.com:invalid"},
        {"public_url": "https://example.com:99999"},
        {"public_url": "https://example.com:0"},
        {"public_url": "https://exa mple.com"},
        {"extra": True},
    ],
)
async def test_invalid_input_keeps_installation_unclaimed(setup_app, client, change):
    _, key, access = setup_app
    response = await client.post(
        "/v1/setup/complete", headers={**access, **signed(key)}, json={**BODY, **change}
    )
    assert response.status_code == 422, response.text
    assert (await client.get("/v1/setup/status")).json()["available"]


async def test_failure_rolls_back_and_retry_recovers(setup_app, client, factory, monkeypatch):
    _, key, access = setup_app
    from identity.services import setup

    original = setup.record

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(setup, "record", fail)
    response = await client.post("/v1/setup/complete", headers={**access, **signed(key)}, json=BODY)
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert "audit unavailable" not in response.text
    async with factory() as db:
        with unfiltered():
            assert list(await db.scalars(select(User))) == []
            assert list(await db.scalars(select(Tenant))) == []
        assert (await db.scalar(select(PlatformInstallation))).completed_at is None
    monkeypatch.setattr(setup, "record", original)
    assert (
        await client.post("/v1/setup/complete", headers={**access, **signed(key)}, json=BODY)
    ).status_code == 200


async def test_existing_tenant_disables_first_run(setup_app, client, factory):
    _, key, access = setup_app
    from tests.factories import build_tenant

    async with factory() as db, db.begin():
        db.add(build_tenant())
    assert not (await client.get("/v1/setup/status")).json()["available"]
    assert (
        await client.post("/v1/setup/complete", headers={**access, **signed(key)}, json=BODY)
    ).status_code == 409


async def test_checks_report_outages_without_details(setup_app, client):
    app, _, access = setup_app
    app.state.redis.ping.side_effect = RuntimeError("private-credential")
    app.state.token_verifier = None
    response = await client.get("/v1/setup/checks", headers=access)
    assert not response.json()["ready"]
    assert "private-credential" not in response.text
    assert [c["status"] for c in response.json()["checks"]] == ["ready", "failed", "failed"]


@pytest.mark.parametrize("reference", ["country", "currency"])
async def test_inactive_defaults_are_not_offered_or_provisioned(
    setup_app, client, factory, reference
):
    from billing_platform.db.reference_models import Country, Currency

    _, key, access = setup_app
    async with factory() as db, db.begin():
        row = await db.get(
            Country if reference == "country" else Currency,
            "IN" if reference == "country" else "INR",
        )
        row.is_active = False
    checks = (await client.get("/v1/setup/checks", headers=access)).json()
    assert not checks["ready"]
    assert checks["countries" if reference == "country" else "currencies"] == []
    response = await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    assert response.status_code == 422
    assert (await client.get("/v1/setup/status")).json()["available"]


async def test_replay_normalizes_surrounding_text_whitespace(setup_app, client):
    _, key, access = setup_app
    headers = {**access, **signed(key)}
    padded = {**BODY, "platform_name": "  JANSO  ", "administrator_name": " First Administrator "}
    first = await client.post("/v1/setup/complete", json=padded, headers=headers)
    assert first.status_code == 200
    assert (
        await client.post("/v1/setup/complete", json=BODY, headers=headers)
    ).json() == first.json()
