from __future__ import annotations

import uuid

import pytest

from tests.test_platform_details import complete
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_setup"]


@pytest.fixture
async def lifecycle_tenant(client, setup_app):
    key, platform = await complete(client, setup_app)
    result = await client.post(
        "/v1/platform/tenants",
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "name": "Lifecycle Workspace",
            "country_code": "IN",
            "administrator_email": "owner@example.com",
            "administrator_name": "Owner",
            "administrator_password": "temporary-secret-for-test",
            "recipient_confirmed": True,
        },
    )
    assert result.status_code == 201, result.text
    tenant = result.json()["id"]
    detail = await client.get(f"/v1/platform/tenants/{tenant}", headers=signed(key))
    assert detail.status_code == 200, detail.text
    return key, platform, tenant, detail.json()


async def test_lifecycle_returns_the_displayed_revision_and_replays_exactly(
    client, lifecycle_tenant
):
    key, _, tenant, detail = lifecycle_tenant
    headers = {**signed(key), "Idempotency-Key": str(uuid.uuid4())}
    body = {
        "status": "suspended",
        "reason": "Administrative access review",
        "expected_updated_at": detail["updated_at"],
    }
    endpoint = f"/v1/platform/tenants/{tenant}/lifecycle"
    first = await client.post(endpoint, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "suspended"
    assert first.json()["updated_at"] != detail["updated_at"]
    second = await client.post(endpoint, headers=headers, json=body)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    changed = await client.post(endpoint, headers=headers, json={**body, "status": "active"})
    assert changed.status_code == 422


async def test_stale_activation_cannot_overwrite_a_newer_access_decision(client, lifecycle_tenant):
    key, _, tenant, detail = lifecycle_tenant
    endpoint = f"/v1/platform/tenants/{tenant}/lifecycle"

    async def change(status, stamp):
        return await client.post(
            endpoint,
            headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
            json={
                "status": status,
                "reason": "Access decision review",
                "expected_updated_at": stamp,
            },
        )

    inactive = await change("suspended", detail["updated_at"])
    assert inactive.status_code == 200, inactive.text
    assert (await change("active", detail["updated_at"])).status_code == 409
    active = await change("active", inactive.json()["updated_at"])
    assert active.status_code == 200, active.text
    assert active.json()["status"] == "active"


async def test_lifecycle_requires_a_reason_revision_and_replay_key(client, lifecycle_tenant):
    key, _, tenant, detail = lifecycle_tenant
    endpoint = f"/v1/platform/tenants/{tenant}/lifecycle"
    body = {
        "status": "suspended",
        "reason": "Access review",
        "expected_updated_at": detail["updated_at"],
    }
    assert (await client.post(endpoint, headers=signed(key), json=body)).status_code == 422
    headers = {**signed(key), "Idempotency-Key": str(uuid.uuid4())}
    for reason in ["   ", "x", "bad\nreason"]:
        assert (
            await client.post(endpoint, headers=headers, json={**body, "reason": reason})
        ).status_code == 422
