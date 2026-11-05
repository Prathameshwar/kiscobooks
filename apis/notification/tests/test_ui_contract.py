"""API contracts needed by notification administration forms and recovery links."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from notification.models import ConsentEvent, NotificationSpace, RecipientEndpoint, Suppression
from notification.ownership import space_scope
from tests.api_support import ACTOR_SECRET, actor_headers
from tests.notif_seed import seed_email_route


@pytest.mark.parametrize("platform", [False, True])
async def test_policy_form_replay_and_masked_endpoint_scope(
    client, app, session, tenant_a, tenant_b, platform
):
    user, subject, endpoint_id = uuid7(), uuid7(), uuid7()
    space = uuid7() if platform else tenant_a
    prefix = "/v1/platform" if platform else "/v1"
    if platform:
        app.state.settings.platform_owner_tenant_id = tenant_a
        app.state.settings.platform_space_id = space

    def proof(path, method="GET", *, tenant=tenant_a, recipient=True, policies=True):
        permissions = [
            "notification.consent.manage",
            "notification.suppression.manage",
            "notification.provider.manage",
        ]
        if not policies:
            permissions = ["notification.provider.read"]
        if recipient:
            permissions.append("notification.recipient.read")
        if platform:
            permissions = [
                "platform." + key.replace("notification.", "notification_", 1)
                for key in permissions
            ]
        result = actor_headers(tenant_id=tenant, user_id=user, permissions=permissions)
        if platform:
            body = json.loads(base64.urlsafe_b64decode(result["X-Actor-Context"] + "=="))
            body.update(
                user_type="platform_notification_operator",
                notification_authority={"path": path, "method": method},
            )
            raw = json.dumps(body).encode()
            result = {
                "X-Actor-Context": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
                "X-Actor-Signature": hmac.new(
                    ACTOR_SECRET.encode(), raw, hashlib.sha256
                ).hexdigest(),
            }
        return result

    with tenant_scope(tenant_a), space_scope(space):
        session.add(
            NotificationSpace(
                id=space, tenant_id=tenant_a, kind="platform" if platform else "tenant"
            )
        )
        session.add(
            RecipientEndpoint(
                id=endpoint_id,
                tenant_id=tenant_a,
                subject_type="platform_recipient" if platform else "user",
                subject_id=subject,
                channel="email",
                destination_hmac=b"x" * 32,
                destination_masked="n***@example.invalid",
                locale="en",
                timezone="UTC",
                verification_status="unverified",
                health_status="healthy",
                source_version=1,
            )
        )
        await session.commit()
    path = f"{prefix}/recipient-endpoints/{endpoint_id}"
    read = await client.get(path, headers=proof(path))
    assert read.status_code == 200 and read.json()["destination_masked"] == "n***@example.invalid"
    assert "destination_ciphertext" not in read.json()
    assert (await client.get(path, headers=proof(path, recipient=False))).status_code == 403
    assert (await client.get(path, headers=proof(path, tenant=tenant_b))).status_code in {403, 404}
    if platform:
        tenant_proof = actor_headers(
            tenant_id=tenant_a, user_id=user, permissions=["notification.recipient.read"]
        )
        assert (
            await client.get(f"/v1/recipient-endpoints/{endpoint_id}", headers=tenant_proof)
        ).status_code == 404
    from notification.config import CredentialBinding

    app.state.settings.credential_bindings["env:BROWSER"] = CredentialBinding(
        tenant_id=tenant_a, space_id=space, environment_variable="BROWSER_TEST_UNUSED"
    )
    binding_path = prefix + "/credential-bindings"
    binding_result = await client.get(binding_path, headers=proof(binding_path))
    assert binding_result.status_code == 200 and "env:BROWSER" in binding_result.json()
    if platform:
        assert binding_result.json() == ["env:BROWSER"]
    now = utcnow()
    consent = {
        "recipient_endpoint_id": str(endpoint_id),
        "purpose": "marketing",
        "state": "granted",
        "source": "console",
        "source_event_key": uuid7().hex,
        "evidence_ref": "evidence-reference",
        "occurred_at": now.isoformat(),
    }
    path = prefix + "/consent-events"
    headers = {**proof(path, "POST"), "Idempotency-Key": "consent-form"}
    first = await client.post(path, headers=headers, json=consent)
    second = await client.post(path, headers=headers, json=consent)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert (
        await client.post(path, headers=headers, json={**consent, "state": "denied"})
    ).status_code == 409
    for change in [
        {"state": "approved-locally"},
        {"expires_at": (now - dt.timedelta(days=1)).isoformat()},
        {"occurred_at": (now + dt.timedelta(days=1)).isoformat()},
    ]:
        assert (
            await client.post(path, headers=proof(path, "POST"), json={**consent, **change})
        ).status_code == 422
    with tenant_scope(tenant_a), space_scope(space):
        assert await session.scalar(select(func.count(ConsentEvent.id))) == 1
    from notification.models import NotificationJob

    with tenant_scope(tenant_a), space_scope(space):
        command_id = await session.scalar(
            select(NotificationJob.id).where(NotificationJob.kind == "consent.record")
        )
    command_path = prefix + f"/jobs/{command_id}"
    assert (await client.get(command_path, headers=proof(command_path))).status_code == 200
    assert (
        await client.get(command_path, headers=proof(command_path, policies=False))
    ).status_code == 403
    path = prefix + "/suppressions"
    body = {
        "channel": "email",
        "destination": "UPPER@Example.invalid",
        "scope_type": "global",
        "reason": "manual",
    }
    headers = {**proof(path, "POST"), "Idempotency-Key": "suppression-form"}
    first = await client.post(path, headers=headers, json=body)
    second = await client.post(path, headers=headers, json=body)
    assert (
        first.status_code == second.status_code == 201 and first.json()["id"] == second.json()["id"]
    )
    assert (
        await client.post(path, headers=headers, json={**body, "reason": "different"})
    ).status_code == 409
    for change in [
        {"scope_type": "event", "scope_key": ""},
        {"valid_to": (now - dt.timedelta(days=1)).isoformat()},
    ]:
        assert (
            await client.post(path, headers=proof(path, "POST"), json={**body, **change})
        ).status_code == 422
    with tenant_scope(tenant_a), space_scope(space):
        from notification.security import keyed_destination_hash

        row = (await session.scalars(select(Suppression))).one()
        assert row.destination_hmac == keyed_destination_hash(
            "upper@example.invalid", app.state.data_key
        )


async def test_route_detail_and_edit_preserve_delivery_policy(client, session, tenant_a, tenant_b):
    from notification.models import RoutingRule

    await seed_email_route(session, tenant=tenant_a, company=uuid7(), subject=uuid7())
    with tenant_scope(tenant_a):
        row = (await session.scalars(select(RoutingRule))).one()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        permissions=["notification.route.read", "notification.route.manage"],
    )
    path = f"/v1/routing-rules/{row.id}"
    result = await client.get(path, headers=headers)
    assert result.status_code == 200
    for key in [
        "max_attempts",
        "timeout_seconds",
        "initial_backoff_seconds",
        "max_backoff_seconds",
    ]:
        assert result.json()[key] == getattr(row, key)
    updated = await client.patch(
        path,
        headers=headers,
        json={
            "expected_updated_at": result.json()["updated_at"],
            "initial_backoff_seconds": 30,
            "max_backoff_seconds": 60,
        },
    )
    assert updated.status_code == 200 and updated.json()["initial_backoff_seconds"] == 30
    assert (
        await client.patch(
            path, headers=headers, json={"initial_backoff_seconds": 100, "max_backoff_seconds": 10}
        )
    ).status_code == 422
    other = actor_headers(
        tenant_id=tenant_b, user_id=uuid7(), permissions=["notification.route.read"]
    )
    assert (await client.get(path, headers=other)).status_code == 404


async def test_route_create_command_replay_does_not_add_duplicate_routes(client, session, tenant_a):
    from notification.models import RoutingRule

    await seed_email_route(session, tenant=tenant_a, company=uuid7(), subject=uuid7())
    with tenant_scope(tenant_a):
        route = (await session.scalars(select(RoutingRule))).one()
    headers = {
        **actor_headers(
            tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.route.manage"]
        ),
        "Idempotency-Key": "route-create-form",
    }
    body = {
        "company_id": str(route.company_id),
        "event_key": "voucher.shared",
        "category": "transactional",
        "channel": "email",
        "provider_account_id": str(route.provider_account_id),
        "sender_identity_id": str(route.sender_identity_id),
        "priority": 0,
        "weight": 1,
        "max_attempts": 3,
        "timeout_seconds": 20,
        "initial_backoff_seconds": 5,
        "max_backoff_seconds": 300,
    }
    first = await client.post("/v1/routing-rules", headers=headers, json=body)
    second = await client.post("/v1/routing-rules", headers=headers, json=body)
    assert (
        first.status_code == second.status_code == 201 and first.json()["id"] == second.json()["id"]
    )
    assert (
        await client.post("/v1/routing-rules", headers=headers, json={**body, "weight": 2})
    ).status_code == 409
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(RoutingRule.id))) == 2
