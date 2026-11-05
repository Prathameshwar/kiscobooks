from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select

from identity.models import Outbox, PlatformInstallation, RoleAssignment
from identity.schemas.tenant import TenantUpdate
from tests.test_gap_login import bearer
from tests.test_platform_setup import BODY, signed

pytest_plugins = ["tests.test_platform_setup"]


@pytest.mark.parametrize("name", ["   ", "bad\x00name", "bad\nname"])
def test_tenant_edit_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        TenantUpdate(name=name)


async def test_platform_update_rolls_back_when_audit_fails(client, setup_app, factory):
    key, _ = await complete(client, setup_app)
    with patch(
        "identity.services.platform_details.record", side_effect=RuntimeError("audit unavailable")
    ):
        response = await client.patch(
            "/v1/platform/details",
            headers=signed(key),
            json={"name": "Uncommitted", "public_url": BODY["public_url"]},
        )
        assert response.status_code == 500
        assert response.headers["cache-control"] == "no-store"
        assert "audit unavailable" not in response.text
    async with factory() as db:
        assert (await db.scalar(select(PlatformInstallation))).name == BODY["platform_name"]


async def complete(client, setup_app):
    _, key, access = setup_app
    response = await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    assert response.status_code == 200, response.text
    return key, response.json()


async def test_platform_details_update_preserves_bootstrap_and_audits(client, setup_app, factory):
    key, result = await complete(client, setup_app)
    async with factory() as db:
        before = await db.scalar(select(PlatformInstallation))
        protected = (
            before.request_hash,
            before.administrator_id,
            before.administrator_subject,
            before.tenant_id,
            before.completed_at,
        )
    response = await client.get("/v1/platform/details", headers=signed(key))
    assert response.status_code == 200, response.text
    assert response.json() == {"name": BODY["platform_name"], "public_url": BODY["public_url"]}
    response = await client.patch(
        "/v1/platform/details",
        headers=signed(key),
        json={"name": "  JANSO Retail  ", "public_url": "https://books.example.com/"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "JANSO Retail", "public_url": "https://books.example.com"}
    async with factory() as db:
        after = await db.scalar(select(PlatformInstallation))
        assert (
            after.request_hash,
            after.administrator_id,
            after.administrator_subject,
            after.tenant_id,
            after.completed_at,
        ) == protected
        with tenant_scope(uuid.UUID(result["tenant_id"])):
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "platform.details_updated")
                )
            )
            assert len(events) == 1
            assert set(events[0].payload["changes"]) == {"name", "public_url"}
            assert "books.example.com" not in str(events[0].payload)
    # Metadata changes do not reopen setup or alter the original replay proof.
    assert (await client.get("/v1/setup/status")).json()["completed"]
    assert (
        await client.post("/v1/setup/complete", json=BODY, headers={**setup_app[2], **signed(key)})
    ).status_code == 200


@pytest.mark.parametrize("method", ["get", "patch"])
async def test_details_denies_missing_and_revoked_authority(client, setup_app, factory, method):
    key, result = await complete(client, setup_app)
    kwargs = (
        {"json": {"name": "Change", "public_url": BODY["public_url"]}} if method == "patch" else {}
    )
    assert (await getattr(client, method)("/v1/platform/details", **kwargs)).status_code == 401
    with tenant_scope(uuid.UUID(result["tenant_id"])):
        async with factory() as db, db.begin():
            assignment = await db.scalar(select(RoleAssignment))
            assignment.is_active = False
    assert (
        await getattr(client, method)("/v1/platform/details", headers=signed(key), **kwargs)
    ).status_code == 403


async def test_details_requires_fresh_authentication(client, setup_app):
    key, _ = await complete(client, setup_app)
    headers = bearer(
        key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 900
    )
    assert (await client.get("/v1/platform/details", headers=headers)).status_code == 200
    response = await client.patch(
        "/v1/platform/details",
        headers=headers,
        json={"name": "Change", "public_url": BODY["public_url"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "platform_reauthentication_required"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   ", "public_url": "https://books.example.com"},
        {"name": "bad\u0000name", "public_url": "https://books.example.com"},
        {"name": "Change", "public_url": "http://books.example.com"},
        {"name": "Change", "public_url": "https://user:password@books.example.com"},
        {"name": "Change", "public_url": "https://books.example.com/path"},
        {"name": "Change", "public_url": "https://books.example.com:99999"},
        {"name": "Change", "public_url": "https://books.example.com?token=secret"},
        {
            "name": "Change",
            "public_url": "https://books.example.com",
            "administrator_id": str(uuid.uuid4()),
        },
    ],
)
async def test_details_invalid_input_has_no_effect(client, setup_app, factory, payload):
    key, _ = await complete(client, setup_app)
    response = await client.patch("/v1/platform/details", headers=signed(key), json=payload)
    assert response.status_code == 422, response.text
    async with factory() as db:
        installation = await db.scalar(select(PlatformInstallation))
        assert installation.name == BODY["platform_name"]
