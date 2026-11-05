import base64
import hashlib
import hmac
import json
import uuid

import pytest
from billing_platform.db import tenant_scope

from audit.api.platform_events import safe_evidence
from audit.tasks.consume import handle_event
from tests.api_support import ACTOR_SECRET, actor_headers, grant
from tests.seed import audit_envelope


def headers(
    tenant, permissions, *, configured=True, scope_type="tenant", scope_id=None, user_id=None
):
    result = actor_headers(
        tenant_id=tenant,
        user_id=user_id or uuid.uuid4(),
        grants=[grant(permissions, scope_type=scope_type, scope_id=scope_id)],
    )
    if configured:
        body = json.loads(base64.urlsafe_b64decode(result["X-Actor-Context"] + "=="))
        body["user_type"] = "platform_operator"
        encoded = json.dumps(body).encode()
        result["X-Actor-Context"] = base64.urlsafe_b64encode(encoded).decode().rstrip("=")
        result["X-Actor-Signature"] = hmac.new(
            ACTOR_SECRET.encode(),
            encoded,
            hashlib.sha256,
        ).hexdigest()
    return result


async def test_platform_notification_evidence_is_separate_from_business_audit(
    client, session, tenant_a
):
    for realm in ("platform", "tenant"):
        envelope = audit_envelope(
            tenant_id=tenant_a,
            action="notification.provider_account.updated",
            entity_type="notification.provider_account",
        )
        envelope.payload.update(
            source_service="notification", context={"notification_realm": realm}
        )
        with tenant_scope(tenant_a):
            await handle_event(session, envelope, consumer_name="notification-test")
    await session.commit()
    ordinary = headers(tenant_a, ["audit.read", "activity.read"], configured=False)
    for path in ("/v1/audit-events", "/v1/activity"):
        response = await client.get(path, headers=ordinary)
        assert response.status_code == 200 and len(response.json()["items"]) == 1
    response = await client.get(
        "/v1/platform-events", headers=headers(tenant_a, ["platform.notification_provider.read"])
    )
    assert response.status_code == 200 and len(response.json()["items"]) == 1
    item = response.json()["items"][0]
    assert (
        await client.get(
            f"/v1/audit-events/{item['id']}",
            params={"occurred_at": item["occurred_at"]},
            headers=ordinary,
        )
    ).status_code == 404
    assert (
        await client.get(
            "/v1/platform-events",
            headers=headers(tenant_a, ["platform.notification_template.read"]),
        )
    ).json()["items"] == []


async def test_platform_history_is_exactly_scoped(client, session, tenant_a, tenant_b):
    subject = uuid.uuid4()
    for tenant, action, entity in [
        (tenant_a, "platform.account_decision_completed", "account_review"),
        (tenant_a, "platform.tenant_updated", "tenant"),
        (tenant_a, "company.updated", "company"),
        (tenant_b, "platform.account_decision_completed", "account_review"),
    ]:
        with tenant_scope(tenant):
            envelope = audit_envelope(
                tenant_id=tenant,
                action=action,
                entity_type=entity,
                entity_id=subject,
                category="security",
            )
            envelope = envelope.model_copy(
                update={"payload": {**envelope.payload, "source_service": "identity"}}
            )
            await handle_event(session, envelope, consumer_name="platform-test")
    await session.commit()
    response = await client.get(
        "/v1/platform-events", headers=headers(tenant_a, ["platform.account.read"])
    )
    assert response.status_code == 200
    assert [row["action"] for row in response.json()["items"]] == [
        "platform.account_decision_completed"
    ]
    event = response.json()["items"][0]
    detail = await client.get(
        f'/v1/platform-events/{event["id"]}',
        params={"occurred_at": event["occurred_at"]},
        headers=headers(tenant_a, ["platform.account.read"]),
    )
    assert detail.status_code == 200
    assert (
        await client.get(
            f'/v1/platform-events/{event["id"]}',
            params={"occurred_at": event["occurred_at"]},
            headers=headers(tenant_b, ["platform.account.read"]),
        )
    ).status_code == 404
    assert (
        await client.get(
            f'/v1/platform-events/{event["id"]}',
            headers=headers(tenant_a, ["platform.account.read"]),
        )
    ).status_code == 422


@pytest.mark.parametrize(
    "permissions,configured",
    [
        (["audit.read", "audit.read_security"], True),
        (["platform.account.read"], False),
        ([], True),
    ],
)
async def test_platform_history_denies_unverified_or_unpermitted_actor(
    client, tenant_a, permissions, configured
):
    assert (
        await client.get(
            "/v1/platform-events",
            headers=headers(
                tenant_a,
                permissions,
                configured=configured,
            ),
        )
    ).status_code == 403


async def test_platform_detail_and_cursor_cannot_bypass_scope(client, session, tenant_a):
    events = []
    with tenant_scope(tenant_a):
        for action, entity in [
            ("platform.account_decision_requested", "account_review"),
            ("platform.account_decision_completed", "account_review"),
            ("platform.tenant_updated", "tenant"),
            ("company.updated", "company"),
        ]:
            envelope = audit_envelope(
                tenant_id=tenant_a,
                action=action,
                entity_type=entity,
                category="security",
                changes={"status": "approved", "email": "private@example.invalid"},
            )
            envelope = envelope.model_copy(
                update={
                    "payload": {
                        **envelope.payload,
                        "source_service": "identity",
                        "reason": "private reason",
                        "context": {"secret": "private"},
                    }
                }
            )
            result = await handle_event(session, envelope, consumer_name="platform-detail")
            events.append((result.event_id, envelope.occurred_at))
    await session.commit()
    user = uuid.uuid4()
    proof = headers(tenant_a, ["platform.account.read"], user_id=user)
    for event_id, occurred_at in events[2:]:
        response = await client.get(
            f"/v1/platform-events/{event_id}",
            params={"occurred_at": occurred_at.isoformat()},
            headers=proof,
        )
        assert response.status_code == 404
    detail = await client.get(
        f"/v1/platform-events/{events[0][0]}",
        params={"occurred_at": events[0][1].isoformat()},
        headers=proof,
    )
    assert detail.status_code == 200
    assert detail.json()["changes"]["status"] == "approved"
    assert "private" not in detail.text
    page = await client.get("/v1/platform-events?limit=1", headers=proof)
    cursor = page.json()["page"]["next_cursor"]
    assert cursor
    assert (
        await client.get(
            "/v1/platform-events",
            params={"limit": 1, "cursor": cursor},
            headers=headers(tenant_a, ["platform.tenant.read"], user_id=user),
        )
    ).status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "company_id=bad",
        "tenant_id=bad",
        "limit=201",
        "entity_type=company",
        "limit=1&limit=2",
        "sort=action",
    ],
)
async def test_platform_history_rejects_unsupported_scope_and_queries(client, tenant_a, query):
    response = await client.get(
        "/v1/platform-events?" + query, headers=headers(tenant_a, ["platform.account.read"])
    )
    assert response.status_code == 422


async def test_platform_history_requires_signature_and_tenant_scope(client, tenant_a):
    assert (await client.get("/v1/platform-events")).status_code == 401
    forged = headers(tenant_a, ["platform.account.read"])
    forged["X-Actor-Signature"] = "0" * 64
    assert (await client.get("/v1/platform-events", headers=forged)).status_code == 401
    assert (
        await client.get(
            "/v1/platform-events",
            headers=headers(
                tenant_a, ["platform.account.read"], scope_type="company", scope_id=uuid.uuid4()
            ),
        )
    ).status_code == 403


async def test_platform_history_rejects_wrong_source_and_business_scope(client, session, tenant_a):
    with tenant_scope(tenant_a):
        for source, company in [("identity", None), ("catalog", None), ("identity", uuid.uuid4())]:
            envelope = audit_envelope(
                tenant_id=tenant_a,
                entity_type="tenant",
                action="platform.tenant_updated",
                category="admin",
            )
            envelope = envelope.model_copy(
                update={
                    "payload": {
                        **envelope.payload,
                        "source_service": source,
                        "company_id": str(company) if company else None,
                    }
                }
            )
            await handle_event(session, envelope, consumer_name="platform-provenance")
    await session.commit()
    response = await client.get(
        "/v1/platform-events", headers=headers(tenant_a, ["platform.tenant.read"])
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", {"from": "active", "to": "suspended"}),
        ("attested", True),
        ("needs_attention", False),
        ("count", 0),
        ("version", 3),
        ("command_id", "00000000-0000-4000-8000-000000000001"),
        ("kind", "country"),
        ("code", "IN"),
        ("error_code", "provider_unavailable"),
    ],
)
def test_platform_evidence_preserves_only_safe_reference_facts(key, value):
    assert safe_evidence({key: value}) == {key: value}


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "private status"),
        ("count", True),
        ("count", -1),
        ("count", 2**63),
        ("command_id", "not-a-uuid"),
        ("kind", {}),
        ("code", "private@example.invalid"),
        ("error_code", "private error"),
        ("email", {"from": "private", "to": "private"}),
        ("version", {}),
        ("status", {"from": "active", "to": None}),
    ],
)
def test_platform_evidence_redacts_legacy_or_malformed_values(key, value):
    assert safe_evidence({key: value}) == {key: {"changed": True}}


@pytest.mark.parametrize(
    "action",
    [
        "platform.tenant_administrator_invited",
        "platform.tenant_administrator_password_recovery_requested",
    ],
)
async def test_tenant_administrator_history_requires_its_explicit_platform_permission(
    client, session, tenant_a, tenant_b, action
):
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            envelope = audit_envelope(
                tenant_id=tenant,
                action=action,
                entity_type="tenant",
            )
            envelope.payload.update(source_service="identity")
            await handle_event(session, envelope, consumer_name="platform-access-test")
    await session.commit()
    for permissions, count in [(["platform.tenant_access.read"], 1), (["platform.tenant.read"], 0)]:
        response = await client.get("/v1/platform-events", headers=headers(tenant_a, permissions))
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == count
    response = await client.get(
        "/v1/platform-events",
        headers=headers(tenant_a, ["platform.tenant_access.read"], configured=False),
    )
    assert response.status_code == 403
