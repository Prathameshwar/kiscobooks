"""HTTP tests for the management surface (Phases 4-6): CRUD + the key invariants
(template-version immutability, activation-overlap lock, consent supersede)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import ProviderAccount, RecipientEndpoint
from tests.api_support import actor_headers

pytestmark = pytest.mark.asyncio


def _headers(tenant: uuid.UUID, perms: list[str]) -> dict[str, str]:
    return actor_headers(tenant_id=tenant, user_id=uuid7(), permissions=perms)


async def _seed_provider(
    session: AsyncSession, tenant: uuid.UUID, channel: str = "email"
) -> uuid.UUID:
    pid = uuid7()
    with unfiltered():
        session.add(
            ProviderAccount(
                id=pid,
                tenant_id=tenant,
                status="active",
                key="ses",
                callback_key="c" * 43,
                channel=channel,
                provider_key="ses" if channel == "email" else "meta",
                display_name="SES",
                credential_ref="env:SES",
            )
        )
        await session.commit()
    return pid


async def _seed_endpoint(session: AsyncSession, tenant: uuid.UUID) -> uuid.UUID:
    eid = uuid7()
    with unfiltered():
        session.add(
            RecipientEndpoint(
                id=eid,
                tenant_id=tenant,
                subject_type="user",
                subject_id=uuid7(),
                channel="email",
                destination_hmac=b"e" * 32,
                destination_masked="a***@x.com",
                locale="en-IN",
                timezone="Asia/Kolkata",
                verification_status="verified",
                health_status="healthy",
                source_version=1,
            )
        )
        await session.commit()
    return eid


async def test_sender_identity_and_routing_rule(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    provider = await _seed_provider(session, tenant_a)
    manage = _headers(tenant_a, ["notification.provider.manage", "notification.route.manage"])
    sender = await client.post(
        "/v1/sender-identities",
        json={
            "provider_account_id": str(provider),
            "key": "noreply",
            "sender_type": "email",
            "external_sender_id": "noreply@acme.example",
            "display_name": "Acme",
        },
        headers=manage,
    )
    assert sender.status_code == 201, sender.text
    sender_id = sender.json()["id"]

    rule = await client.post(
        "/v1/routing-rules",
        json={
            "company_id": str(uuid7()),
            "event_key": "invoice.posted",
            "category": "transactional",
            "channel": "email",
            "provider_account_id": str(provider),
            "sender_identity_id": sender_id,
            "priority": 1,
            "weight": 1,
            "max_attempts": 3,
            "timeout_seconds": 10,
            "initial_backoff_seconds": 5,
            "max_backoff_seconds": 300,
        },
        headers=manage,
    )
    assert rule.status_code == 201, rule.text


async def test_sender_identity_without_permission_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    provider = await _seed_provider(session, tenant_a)
    resp = await client.post(
        "/v1/sender-identities",
        json={
            "provider_account_id": str(provider),
            "key": "x",
            "sender_type": "email",
            "external_sender_id": "x@y.com",
            "display_name": "X",
        },
        headers=_headers(tenant_a, ["notification.provider.read"]),
    )
    assert resp.status_code == 403


async def test_suppression_stores_hmac_and_expires(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    manage = _headers(tenant_a, ["notification.suppression.manage"])
    created = await client.post(
        "/v1/suppressions",
        json={
            "channel": "email",
            "destination": "spam@x.com",
            "scope_type": "global",
            "reason": "complaint",
        },
        headers=manage,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert "destination" not in body  # raw destination never returned
    listed = await client.get("/v1/suppressions", headers=manage)
    assert created.json()["id"] in {i["id"] for i in listed.json()["items"]}
    expired = await client.post(f"/v1/suppressions/{body['id']}/expire", headers=manage)
    assert expired.status_code == 200
    assert expired.json()["valid_to"] is not None


async def test_consent_record_supersedes_state(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    endpoint = await _seed_endpoint(session, tenant_a)
    manage = _headers(tenant_a, ["notification.consent.manage"])

    def record(state: str, when: str, key: str) -> dict[str, object]:
        return {
            "recipient_endpoint_id": str(endpoint),
            "purpose": "marketing",
            "state": state,
            "source": "portal",
            "source_event_key": key,
            "occurred_at": when,
        }

    first = await client.post(
        "/v1/consent-events", json=record("granted", "2026-01-01T00:00:00Z", "c1"), headers=manage
    )
    assert first.status_code == 201
    assert first.json()["state"] == "granted"
    second = await client.post(
        "/v1/consent-events", json=record("withdrawn", "2026-02-01T00:00:00Z", "c2"), headers=manage
    )
    assert second.json()["state"] == "withdrawn"  # later event supersedes
    states = await client.get(
        f"/v1/consent-states?recipient_endpoint_id={endpoint}", headers=manage
    )
    assert [s["state"] for s in states.json()["items"]] == ["withdrawn"]


async def test_template_version_immutability_and_activation_overlap(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    manage = _headers(tenant_a, ["notification.template.manage"])
    template = await client.post(
        "/v1/templates",
        json={
            "company_id": str(uuid7()),
            "key": "inv",
            "event_key": "invoice.posted",
            "category": "transactional",
            "default_locale": "en-IN",
        },
        headers=manage,
    )
    tid = template.json()["id"]
    variant = await client.post(
        f"/v1/templates/{tid}/variants",
        json={"channel": "email", "locale": "en-IN"},
        headers=manage,
    )
    vid = variant.json()["id"]

    v1 = await client.post(
        f"/v1/variants/{vid}/versions",
        json={"subject_text": "Hi", "body_text": "Hello {{ name }}"},
        headers=manage,
    )
    assert v1.status_code == 201 and v1.json()["version"] == 1
    # Identical content is rejected (immutable content hash unique per variant).
    dup = await client.post(
        f"/v1/variants/{vid}/versions",
        json={"subject_text": "Hi", "body_text": "Hello {{ name }}"},
        headers=manage,
    )
    assert dup.status_code == 409
    # Different content gets the next version number.
    v2 = await client.post(
        f"/v1/variants/{vid}/versions",
        json={"subject_text": "Hi", "body_text": "Hello again {{ name }}"},
        headers=manage,
    )
    assert v2.status_code == 201 and v2.json()["version"] == 2

    a1 = await client.post(
        f"/v1/variants/{vid}/activations",
        json={
            "template_version_id": v1.json()["id"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-06-01T00:00:00Z",
        },
        headers=manage,
    )
    assert a1.status_code == 201
    # An overlapping window is rejected.
    overlap = await client.post(
        f"/v1/variants/{vid}/activations",
        json={"template_version_id": v2.json()["id"], "valid_from": "2026-03-01T00:00:00Z"},
        headers=manage,
    )
    assert overlap.status_code == 409
    # A non-overlapping later window is accepted.
    later = await client.post(
        f"/v1/variants/{vid}/activations",
        json={"template_version_id": v2.json()["id"], "valid_from": "2026-06-02T00:00:00Z"},
        headers=manage,
    )
    assert later.status_code == 201


async def test_binding_create_and_approve(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    provider = await _seed_provider(session, tenant_a, "whatsapp")
    manage = _headers(tenant_a, ["notification.template.manage"])
    template = await client.post(
        "/v1/templates",
        json={
            "company_id": str(uuid7()),
            "key": "wa",
            "event_key": "invoice.posted",
            "category": "transactional",
            "default_locale": "en",
        },
        headers=manage,
    )
    variant = await client.post(
        f"/v1/templates/{template.json()['id']}/variants",
        json={"channel": "whatsapp", "locale": "en"},
        headers=manage,
    )
    version = await client.post(
        f"/v1/variants/{variant.json()['id']}/versions",
        json={"body_text": "hi"},
        headers=manage,
    )
    binding = await client.post(
        f"/v1/template-versions/{version.json()['id']}/bindings",
        json={
            "template_version_id": version.json()["id"],
            "provider_account_id": str(provider),
            "external_template_id": "wa_tmpl_1",
            "external_name": "invoice",
            "external_language": "en",
        },
        headers=manage,
    )
    assert binding.status_code == 201 and binding.json()["approval_status"] == "pending"
    approved = await client.patch(
        f"/v1/bindings/{binding.json()['id']}", json={"approval_status": "approved"}, headers=manage
    )
    # Administrators configure bindings; approval comes only from provider sync.
    assert approved.status_code == 422
    sync = await client.post(
        f"/v1/bindings/{binding.json()['id']}/sync",
        headers={**manage, "Idempotency-Key": "binding-sync"},
    )
    assert sync.status_code == 202 and sync.json()["status"] == "pending"
