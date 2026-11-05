import base64
import json
import uuid
from unittest.mock import patch

from billing_platform.db import tenant_scope
from sqlalchemy import select

from identity.models import Outbox, RoleAssignment
from tests.test_platform_setup import BODY, signed

pytest_plugins = ["tests.test_platform_setup"]


async def complete(client, setup_app):
    app, key, access = setup_app
    response = await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    assert response.status_code == 200
    return app, key, uuid.UUID(response.json()["tenant_id"])


async def test_notification_gateway_authority_is_bound_to_method_and_path(client, setup_app):
    _, key, _ = await complete(client, setup_app)
    path = "/notification/v1/platform/provider-accounts"
    proof = {**signed(key), "X-Original-URI": path, "X-Original-Method": "GET"}
    response = await client.get("/internal/v1/gateway/authorize", headers=proof)
    assert response.status_code == 204
    context = json.loads(base64.urlsafe_b64decode(response.headers["x-actor-context"] + "=="))
    assert context["notification_authority"] == {
        "path": "/v1/platform/provider-accounts",
        "method": "GET",
    }
    from billing_platform.errors import PermissionDeniedError

    with patch(
        "identity.api.platform.fresh_platform_actor", side_effect=PermissionDeniedError("expired")
    ):
        response = await client.get(
            "/internal/v1/gateway/authorize", headers={**proof, "X-Original-Method": "POST"}
        )
        assert response.status_code == 403


async def test_gateway_platform_marker_requires_configured_operator_and_live_grants(
    client, setup_app, factory
):
    _, key, tenant = await complete(client, setup_app)
    request_headers = {**signed(key), "X-Original-URI": "/audit/v1/platform-events"}
    response = await client.get("/internal/v1/gateway/authorize", headers=request_headers)
    assert response.status_code == 204, response.text
    context = json.loads(base64.urlsafe_b64decode(response.headers["x-actor-context"] + "=="))
    assert context["user_type"] == "platform_operator"
    assert "audit.read_security" not in str(context["grants"])
    assert "audit.read" not in str(context["grants"])
    from billing_platform.errors import PermissionDeniedError

    with patch(
        "identity.services.platform_audit.platform_actor",
        side_effect=PermissionDeniedError("unconfigured"),
    ):
        assert (
            await client.get("/internal/v1/gateway/authorize", headers=request_headers)
        ).status_code == 403
    async with factory() as db, db.begin():
        with tenant_scope(tenant):
            for row in await db.scalars(select(RoleAssignment)):
                row.is_active = False
    assert (
        await client.get("/internal/v1/gateway/authorize", headers=request_headers)
    ).status_code == 403


async def test_tenant_mutations_keep_operating_and_affected_tenant_evidence(
    client, setup_app, factory
):
    _, key, operating = await complete(client, setup_app)
    body = {
        "name": "New workspace",
        "administrator_email": "owner@example.invalid",
        "administrator_name": "Owner",
        "country_code": "IN",
        "currency_code": "INR",
        "administrator_password": "temporary-secret-for-test",
        "recipient_confirmed": True,
    }
    proof = {**signed(key), "Idempotency-Key": "platform-audit-provision"}
    response = await client.post("/v1/platform/tenants", json=body, headers=proof)
    assert response.status_code == 201, response.text
    target = uuid.UUID(response.json()["id"])
    assert (await client.post("/v1/platform/tenants", json=body, headers=proof)).status_code == 201
    response = await client.patch(
        f"/v1/platform/tenants/{target}", json={"name": "Updated"}, headers=signed(key)
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/v1/platform/tenants/{target}/lifecycle",
        json={
            "status": "suspended",
            "reason": "Private support details",
            "expected_updated_at": response.json()["updated_at"],
        },
        headers={**signed(key), "X-Trace-Id": "a" * 32, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    async with factory() as db:
        with tenant_scope(operating):
            rows = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type.in_(
                            {
                                "platform.tenant_provisioned",
                                "platform.tenant_updated",
                                "platform.tenant_lifecycle_changed",
                            }
                        )
                    )
                )
            )
            assert len(rows) == 3
            assert all(row.payload["entity_id"] == str(target) for row in rows)
            lifecycle = next(row for row in rows if row.event_type.endswith("lifecycle_changed"))
            assert lifecycle.payload["changes"]["status"] == {"from": "active", "to": "suspended"}
            assert "Private" not in str(lifecycle.payload)
            assert lifecycle.payload["request_id"]
            assert lifecycle.trace_id == "a" * 32
            assert response.headers["cache-control"] == "no-store"
        with tenant_scope(target):
            assert await db.scalar(
                select(Outbox.id).where(Outbox.event_type == "tenant.lifecycle_changed")
            )


async def test_failed_platform_event_rolls_back_tenant_creation(client, setup_app, factory, caplog):
    await complete(client, setup_app)
    with patch("identity.api.platform.record", side_effect=RuntimeError("private@example.invalid")):
        response = await client.post(
            "/v1/platform/tenants",
            headers={**signed(setup_app[1]), "Idempotency-Key": "rollback"},
            json={
                "name": "Uncommitted",
                "administrator_name": "Owner",
                "administrator_email": "owner@example.invalid",
                "country_code": "IN",
                "administrator_password": "temporary-secret-for-test",
                "recipient_confirmed": True,
            },
        )
        assert response.status_code == 500
        assert response.json()["error"]["message"] == "Platform request failed"
        assert response.headers["cache-control"] == "no-store"
        assert "private@example.invalid" not in response.text
    from billing_platform.db import unfiltered

    from identity.models import Tenant

    async with factory() as db:
        with unfiltered():
            assert await db.scalar(select(Tenant.id).where(Tenant.name == "Uncommitted")) is None
    diagnostic = next(
        json.loads(row.message)
        for row in caplog.records
        if "platform.request_failed" in row.message
    )
    assert diagnostic["service"] == "identity"
    assert diagnostic["error_type"] == "RuntimeError"
    assert "private@example.invalid" not in caplog.text
