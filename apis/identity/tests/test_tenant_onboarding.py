from __future__ import annotations

import time
import uuid

from billing_platform.db import tenant_scope, unfiltered
from sqlalchemy import select

from identity.models import IdempotencyKey, Outbox, RoleAssignment, Tenant, User
from tests.test_gap_login import bearer
from tests.test_platform_setup import BODY

pytest_plugins = ["tests.test_platform_setup"]


def signed(key, **claims):
    return bearer(
        key,
        **{
            "email": "admin@example.com",
            "email_verified": True,
            "auth_time": int(time.time()),
            **claims,
        },
    )


WORKSPACE = {
    "name": "New business",
    "administrator_name": "Owner",
    "country_code": "IN",
    "currency_code": "INR",
    "timezone": "Asia/Kolkata",
}
PLATFORM_WORKSPACE = {
    **WORKSPACE,
    "administrator_password": "temporary-secret-for-test",
    "recipient_confirmed": True,
}


async def initialize(setup_app, client):
    app, key, access = setup_app
    response = await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    assert response.status_code == 200
    return app, key


async def test_self_provision_replay_and_isolation(setup_app, client, factory):
    _, key = await initialize(setup_app, client)
    headers = signed(key, subject="new-owner", email="new@example.invalid")
    onboarding = (await client.get("/v1/onboarding/status", headers=headers)).json()
    assert onboarding["linked"] is False
    assert onboarding["options"]["countries"][0]["code"] == "IN"
    first = await client.post("/v1/onboarding/tenant", headers=headers, json=WORKSPACE)
    assert first.status_code == 201, first.text
    tenant_id = uuid.UUID(first.json()["id"])
    replay = await client.post("/v1/onboarding/tenant", headers=headers, json=WORKSPACE)
    assert replay.status_code == 201 and replay.json()["id"] == str(tenant_id)
    changed = await client.post(
        "/v1/onboarding/tenant", headers=headers, json={**WORKSPACE, "name": "Changed request"}
    )
    assert changed.status_code == 409
    assert (
        await client.post(
            "/v1/onboarding/tenant", headers=headers, json={**WORKSPACE, "slug": "another-business"}
        )
    ).status_code == 422
    session = await client.get("/v1/session", headers=headers)
    assert session.status_code == 200
    permissions = session.json()["permissions"]
    assert "user.invite" in permissions and "platform.tenant.create" not in permissions
    assert (await client.get("/v1/platform/tenants", headers=headers)).status_code == 403
    assert (await client.get("/v1/platform/tenant-options", headers=headers)).status_code == 403
    async with factory() as db:
        with tenant_scope(tenant_id):
            users = list(await db.scalars(select(User)))
            grants = list(await db.scalars(select(RoleAssignment)))
            assert len(users) == len(grants) == 1
            assert users[0].authentik_sub == "new-owner" and users[0].status == "active"
            assert users[0].email_verified_at is not None
            assert len(list(await db.scalars(select(Outbox)))) >= 3


async def test_onboarding_denies_unverified_stale_bound_and_mass_assignment(setup_app, client):
    _, key = await initialize(setup_app, client)
    for claims in [
        {"email_verified": False},
        {"auth_time": int(time.time()) - 301},
        {"org_id": str(uuid.uuid4())},
    ]:
        response = await client.post(
            "/v1/onboarding/tenant",
            json=WORKSPACE,
            headers=signed(key, subject="new-owner", **claims),
        )
        assert response.status_code in {401, 403}
    assert (await client.post("/v1/onboarding/tenant", json=WORKSPACE)).status_code == 401
    assert (
        await client.post(
            "/v1/onboarding/tenant",
            json={**WORKSPACE, "role": "platform_admin"},
            headers=signed(key, subject="new-owner"),
        )
    ).status_code == 422


async def test_platform_create_ready_administrator_and_own_suspend_guard(
    setup_app, client, factory, monkeypatch
):
    app, key = await initialize(setup_app, client)
    app.state.settings.public_auth_url = "http://localhost:4310"
    headers = {**signed(key), "Idempotency-Key": "admin-create"}
    app.state.settings.notification_platform_tenant_id = uuid.uuid4()
    body = {**PLATFORM_WORKSPACE, "administrator_email": "invite@example.invalid"}
    created = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "no-store"
    tenant_id = created.json()["id"]
    detail = await client.get(f"/v1/platform/tenants/{tenant_id}", headers=headers)
    assert detail.status_code == 200 and detail.json()["suspended_reason"] is None
    assert created.json()["administrator_password"] == PLATFORM_WORKSPACE["administrator_password"]
    assert created.json()["sign_in_url"] == "http://localhost:4310/login"
    assert created.json()["notification_status"] == "manual"
    replay = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert replay.status_code == 201 and replay.json()["administrator_password"] is None
    from identity.services.administrator_provider import AdministratorProvider

    async def unexpected_create(self, **kwargs):
        raise AssertionError("a changed replay must not create a provider account")

    monkeypatch.setattr(AdministratorProvider, "create", unexpected_create)
    changed = await client.post(
        "/v1/platform/tenants",
        headers=headers,
        json={**body, "administrator_email": "different@example.invalid"},
    )
    assert changed.status_code == 422
    async with factory() as db:
        with tenant_scope(uuid.UUID(tenant_id)):
            administrator = await db.scalar(select(User))
            assert administrator.status == "active" and administrator.authentik_sub
            assert administrator.email_verified_at is not None
        with unfiltered():
            receipt = await db.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.endpoint == "identity.platform.tenant.provision"
                )
            )
            assert receipt is not None
            assert body["administrator_password"] not in str(receipt.response_body)
            assert all(
                body["administrator_password"] not in str(row.payload)
                for row in await db.scalars(select(Outbox))
            )
    updated = await client.patch(
        f"/v1/platform/tenants/{tenant_id}",
        headers=headers,
        json={"name": "Renamed business", "default_timezone": "Asia/Kolkata"},
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Renamed business"
    assert (
        await client.patch(
            f"/v1/platform/tenants/{tenant_id}", headers=headers, json={"slug": "changed"}
        )
    ).status_code == 422
    assert (
        await client.patch(
            f"/v1/platform/tenants/{tenant_id}",
            headers=headers,
            json={"default_timezone": "Bad/Timezone"},
        )
    ).status_code == 422
    own = (await client.get("/v1/session", headers=headers)).json()["tenant"]["id"]
    assert (
        await client.post(
            f"/v1/platform/tenants/{own}/lifecycle",
            headers=headers,
            json={
                "status": "suspended",
                "reason": "test",
                "expected_updated_at": "2026-10-26T00:00:00Z",
            },
        )
    ).status_code == 403
    async with factory() as db:
        with unfiltered():
            assert len(list(await db.scalars(select(Tenant)))) == 2


async def test_platform_directory_survives_old_login_but_mutations_require_fresh_proof(
    setup_app, client
):
    _, key = await initialize(setup_app, client)
    stale = signed(key, auth_time=int(time.time()) - 601)
    listing = await client.get("/v1/platform/tenants", headers=stale)
    assert listing.status_code == 200, listing.text
    creation = await client.post(
        "/v1/platform/tenants",
        headers={**stale, "Idempotency-Key": "stale"},
        json={**PLATFORM_WORKSPACE, "administrator_email": "invite@example.invalid"},
    )
    assert creation.status_code == 403
    assert creation.json()["error"]["code"] == "platform_reauthentication_required"
    denied = await client.get("/v1/platform/tenants", headers=signed(key, subject="unknown"))
    assert denied.status_code in {401, 403}


async def test_platform_can_select_only_unlinked_verified_existing_user(
    setup_app, client, monkeypatch
):
    app, key = await initialize(setup_app, client)
    app.state.settings.public_auth_url = "http://localhost:4310"
    from identity.services.administrator_provider import AdministratorProvider

    row = {
        "pk": 9,
        "uid": "d" * 64,
        "username": "existing-owner",
        "name": "Existing Owner",
        "email": "existing@example.invalid",
        "type": "external",
        "is_active": True,
        "is_superuser": False,
        "groups": [],
        "roles": [],
        "attributes": {"billing_email_verified": True},
    }

    async def by_email(self, email):
        return row if email == row["email"] else None

    monkeypatch.setattr(AdministratorProvider, "by_email", by_email)
    headers = signed(key)
    available = await client.get(
        "/v1/platform/tenant-administrators/available",
        params={"email": row["email"]},
        headers=headers,
    )
    assert available.status_code == 200
    assert available.json()["available"]["username"] == "existing-owner"
    assert (
        await client.get(
            "/v1/platform/tenant-administrators/available", params={"email": row["email"]}
        )
    ).status_code == 401
    denied = await client.get(
        "/v1/platform/tenant-administrators/available",
        params={"email": row["email"]},
        headers=signed(key, subject="unknown"),
    )
    assert denied.status_code in {401, 403}
    invalid = await client.get(
        "/v1/platform/tenant-administrators/available",
        params={"email": "bad-address"},
        headers=headers,
    )
    assert invalid.status_code == 422
    created = await client.post(
        "/v1/platform/tenants",
        headers={**headers, "Idempotency-Key": "existing-owner"},
        json={**WORKSPACE, "administrator_email": row["email"], "administrator_mode": "existing"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["administrator_password"] is None
    unavailable = await client.get(
        "/v1/platform/tenant-administrators/available",
        params={"email": row["email"]},
        headers=headers,
    )
    assert unavailable.json()["available"] is None
    duplicate = await client.post(
        "/v1/platform/tenants",
        headers={**headers, "Idempotency-Key": "other-tenant"},
        json={**WORKSPACE, "administrator_email": row["email"], "administrator_mode": "existing"},
    )
    assert duplicate.status_code == 409


async def test_provider_activation_failure_retries_one_committed_tenant(
    setup_app, client, factory, monkeypatch
):
    app, key = await initialize(setup_app, client)
    app.state.settings.public_auth_url = "http://localhost:4310"
    from identity.services.administrator_provider import (
        AdministratorProvider,
        AdministratorProviderUnavailableError,
    )

    attempts = 0

    async def activate(self, *, email, marker, subject):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AdministratorProviderUnavailableError("Activation unavailable")

    monkeypatch.setattr(AdministratorProvider, "activate", activate)
    headers = {**signed(key), "Idempotency-Key": "activation-retry"}
    body = {**PLATFORM_WORKSPACE, "administrator_email": "retry@example.invalid"}
    failed = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert failed.status_code == 503
    replay = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert replay.status_code == 201, replay.text
    assert replay.json()["administrator_password"] is None
    assert attempts == 2
    async with factory() as db:
        with unfiltered():
            assert len(list(await db.scalars(select(Tenant)))) == 2


async def test_directory_search_filters_stable_sort_and_bound_cursors(setup_app, client):
    app, key = await initialize(setup_app, client)
    app.state.settings.public_auth_url = "http://localhost:4310"
    for slug, name in [("beta", "Beta"), ("alpha", "Alpha"), ("alpine", "Alpine")]:
        created = await client.post(
            "/v1/platform/tenants",
            headers={**signed(key), "Idempotency-Key": slug},
            json={
                **PLATFORM_WORKSPACE,
                "name": name,
                "administrator_email": "invite@example.invalid",
            },
        )
        assert created.status_code == 201
    headers = signed(key)
    options = await client.get("/v1/platform/tenant-options", headers=headers)
    assert options.status_code == 200 and options.json()["currencies"][0]["code"] == "INR"
    first = await client.get("/v1/platform/tenants?q=Al&sort=name&limit=1", headers=headers)
    assert [row["name"] for row in first.json()["items"]] == ["Alpha"]
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(
        "/v1/platform/tenants",
        headers=headers,
        params={"q": "Al", "sort": "name", "limit": 1, "cursor": cursor},
    )
    assert [row["name"] for row in second.json()["items"]] == ["Alpine"]
    invalid = await client.get(
        "/v1/platform/tenants",
        headers=headers,
        params={"q": "Be", "sort": "name", "cursor": cursor},
    )
    assert invalid.status_code == 422
    assert (
        await client.get("/v1/platform/tenants?sort=primary_contact_email", headers=headers)
    ).status_code == 422
    assert (
        await client.get("/v1/platform/tenants?status=invalid", headers=headers)
    ).status_code == 422
    assert (await client.get("/v1/platform/tenants?q=%25%25", headers=headers)).json()[
        "items"
    ] == []
    assert (await client.get("/v1/platform/tenants?status=suspended", headers=headers)).json()[
        "items"
    ] == []
