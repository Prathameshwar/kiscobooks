"""Reusable joined operator workflows; all writes stay in isolated fixture databases.

Provider creation is the existing setup fixture's fake adapter. These are API
acceptance checks, not proof of real Authentik, email, or broker delivery.
"""

from __future__ import annotations

import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from pydantic import SecretStr
from sqlalchemy import select

from identity.models import Outbox, User
from identity.services.administrator_recovery import AdministratorRecoveryProvider
from tests.test_administrator_recovery import SUBJECT, TOKEN, provider_settings, provider_user
from tests.test_platform_access import admin_detail, change_body
from tests.test_platform_details import complete
from tests.test_platform_pricing import BODY as PRICE
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_setup"]


def command_headers(key):
    return {**signed(key), "Idempotency-Key": str(uuid.uuid4())}


def tenant_body(**overrides):
    # Credential is generated for this isolated adapter; no real account is created.
    return {
        "name": "QA Acceptance Workspace",
        "country_code": "IN",
        "currency_code": "INR",
        "administrator_email": "owner@example.invalid",
        "administrator_name": "QA Owner",
        "administrator_password": uuid.uuid4().hex,
        "recipient_confirmed": True,
        **overrides,
    }


async def test_joined_tenant_and_administrator_workflow(client, setup_app, factory):
    key, platform = await complete(client, setup_app)
    headers, body = command_headers(key), tenant_body()
    created = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert created.status_code == 201, created.text
    tenant = created.json()["id"]
    replay = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert replay.status_code == 201
    # The credential is deliberately returned only once; replay must not expose it.
    assert replay.json() == {**created.json(), "administrator_password": None}
    path = f"/v1/platform/tenants/{tenant}"
    edited = await client.patch(path, headers=signed(key), json={"name": "QA Reviewed Workspace"})
    assert edited.status_code == 200, edited.text
    listing = await client.get("/v1/platform/tenants?q=QA%20Reviewed", headers=signed(key))
    assert tenant in [row["id"] for row in listing.json()["items"]]
    for status in ("suspended", "active"):
        detail = (await client.get(path, headers=signed(key))).json()
        payload = {
            "status": status,
            "reason": "QA joined acceptance lifecycle",
            "expected_updated_at": detail["updated_at"],
        }
        proof = command_headers(key)
        changed = await client.post(path + "/lifecycle", headers=proof, json=payload)
        assert changed.status_code == 200, changed.text
        assert changed.json()["status"] == status
        assert (
            await client.post(path + "/lifecycle", headers=proof, json=payload)
        ).json() == changed.json()
    roster_path = f"/v1/platform/access/tenants/{tenant}/administrators"
    roster = (await client.get(roster_path, headers=signed(key))).json()["items"]
    assert len(roster) == 1
    owner = roster[0]["id"]
    detail = await admin_detail(client, key, tenant, owner)
    last_admin = await client.post(
        roster_path + f"/{owner}/commands",
        headers=command_headers(key),
        json=change_body(detail, "revoke"),
    )
    assert last_admin.status_code == 409, last_admin.text
    invite_headers = command_headers(key)
    invite_body = {
        "display_name": "QA Backup",
        "email": "backup@example.invalid",
        "reason": "QA joined acceptance backup",
    }
    invited = await client.post(roster_path, headers=invite_headers, json=invite_body)
    assert invited.status_code == 201, invited.text
    assert (
        await client.post(roster_path, headers=invite_headers, json=invite_body)
    ).json() == invited.json()
    backup = invited.json()["administrator_id"]
    for action in ("resend_invitation", "revoke", "restore"):
        detail = await admin_detail(client, key, tenant, backup)
        response = await client.post(
            roster_path + f"/{backup}/commands",
            headers=command_headers(key),
            json=change_body(detail, action),
        )
        assert response.status_code == 200, response.text
    with tenant_scope(uuid.UUID(platform["tenant_id"])):
        async with factory() as db:
            events = list(
                await db.scalars(select(Outbox).where(Outbox.event_type.startswith("platform.")))
            )
            assert events
            assert all("example.invalid" not in str(event.payload) for event in events)


async def test_joined_pricing_revision_delete_restore_workflow(client, setup_app):
    key, _ = await complete(client, setup_app)
    created = await client.post("/v1/platform/pricing", headers=signed(key), json=PRICE)
    assert created.status_code == 201, created.text
    path = "/v1/platform/pricing/" + created.json()["id"]
    updated = await client.patch(
        path, headers=signed(key), json={**PRICE, "monthly_fee": "389", "expected_version": 1}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["prices"][0]["term_total"] == "5508.24"
    deleted = await client.post(path + "/delete", headers=signed(key), json={"expected_version": 2})
    assert deleted.status_code == 200, deleted.text
    stale_restore = await client.post(
        path + "/restore", headers=signed(key), json={"expected_version": 2}
    )
    assert stale_restore.status_code == 409
    restored = await client.post(
        path + "/restore", headers=signed(key), json={"expected_version": 3}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == 4 and not restored.json()["is_active"]
    history = (await client.get(path + "/revisions", headers=signed(key))).json()["items"]
    assert sorted(row["version"] for row in history) == [1, 2, 3, 4]


@pytest.mark.parametrize("field", ["name", "administrator_name"])
async def test_tenant_creation_rejects_ascii_delete_control_character(client, setup_app, field):
    key, _ = await complete(client, setup_app)
    response = await client.post(
        "/v1/platform/tenants",
        headers=command_headers(key),
        json=tenant_body(**{field: "Invalid\x7fName"}),
    )
    assert (
        response.status_code == 422
    ), f"Control character was accepted: HTTP {response.status_code}"


async def test_tenant_edit_rejects_ascii_delete_control_character(client, setup_app):
    key, _ = await complete(client, setup_app)
    created = await client.post(
        "/v1/platform/tenants", headers=command_headers(key), json=tenant_body()
    )
    assert created.status_code == 201, created.text
    path = "/v1/platform/tenants/" + created.json()["id"]
    response = await client.patch(path, headers=signed(key), json={"name": "Invalid\x7fName"})
    assert (
        response.status_code == 422
    ), f"Control character was persisted: HTTP {response.status_code}"


async def test_provisioned_administrator_can_use_advertised_recovery(client, setup_app, factory):
    """Provisioning's opaque OIDC subject must work with its advertised recovery action."""
    key, _ = await complete(client, setup_app)
    setup_app[0].state.settings.authentik_recovery_url = "https://provider.test"
    setup_app[0].state.settings.authentik_recovery_token = SecretStr(secrets.token_urlsafe(32))
    created = await client.post(
        "/v1/platform/tenants", headers=command_headers(key), json=tenant_body()
    )
    assert created.status_code == 201, created.text
    tenant = created.json()["id"]
    base = f"/v1/platform/access/tenants/{tenant}/administrators"
    roster = await client.get(base, headers=signed(key))
    assert roster.status_code == 200, roster.text
    owner = roster.json()["items"][0]["id"]
    detail = await admin_detail(client, key, tenant, owner)
    assert "link" in detail["recovery_deliveries"]
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db:
            subject = (await db.get(User, uuid.UUID(owner))).authentik_sub
    assert len(subject) == 64
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "results": [
                        provider_user(
                            uid=subject,
                            email=tenant_body()["administrator_email"],
                            path="bill/tenant-administrators",
                            attributes={
                                "billing_email_verified": True,
                                "billing_tenant_provision_command": str(uuid.uuid4()),
                            },
                        )
                    ],
                    "pagination": {"next": 0},
                },
            )
        return httpx.Response(
            200,
            json={
                "link": "https://provider.test/if/flow/bill-administrator-recovery/?flow_token="
                + TOKEN
            },
        )

    app = setup_app[0]
    previous = app.state.oidc_http
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        app.state.oidc_http = http
        try:
            response = await client.post(
                f"{base}/{owner}/password-recovery",
                headers=signed(key),
                json={
                    "delivery": "link",
                    "reason": "QA advertised recovery acceptance",
                    "expected_updated_at": detail["updated_at"],
                    "expected_assignment_updated_at": detail["assignment_updated_at"],
                },
            )
        finally:
            app.state.oidc_http = previous
    assert response.status_code == 200, response.text
    assert len(requests) == 2 and requests[-1].url.path.endswith("/42/recovery/")
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db:
            assert (await db.get(User, uuid.UUID(owner))).authentik_sub == subject


def test_tenant_and_administrator_names_preserve_valid_unicode():
    from identity.api.platform import PlatformTenantProvision
    from identity.schemas.tenant import TenantUpdate

    body = tenant_body(name="  महाराष्ट्र व्यापारी  ", administrator_name="  Prathām सिंह  ")
    assert PlatformTenantProvision(**body).name == "महाराष्ट्र व्यापारी"
    assert PlatformTenantProvision(**body).administrator_name == "Prathām सिंह"
    assert TenantUpdate(name="  महाराष्ट्र व्यापारी  ").name == "महाराष्ट्र व्यापारी"


async def test_recovery_adapter_accepts_platform_provisioned_account_path():
    """Platform provisioning uses bill/tenant-administrators, not signup's path."""

    def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "results": [
                        provider_user(
                            path="bill/tenant-administrators",
                            attributes={
                                "billing_email_verified": True,
                                "billing_tenant_provision_command": str(uuid.uuid4()),
                            },
                        )
                    ],
                    "pagination": {"next": 0},
                },
            )
        return httpx.Response(
            200,
            json={
                "link": "https://provider.test/if/flow/bill-administrator-recovery/?flow_token="
                + TOKEN
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        link, _ = await AdministratorRecoveryProvider(provider_settings(), http).recover(
            SUBJECT, "link", "owner@example.com"
        )
    assert link is not None
