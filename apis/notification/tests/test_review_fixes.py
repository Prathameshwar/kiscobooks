"""Regression evidence for the follow-up notification review."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.models import (
    DeliveryAttempt,
    NotificationPreference,
    NotificationRequest,
    RecipientEndpoint,
)
from notification.providers import SendCommand, SendResult
from notification.tasks.dispatch import Dispatcher
from tests.api_support import actor_headers
from tests.notif_seed import CIPHER, KEY_REF, NOW
from tests.test_normalize import _make_sent_delivery

pytestmark = pytest.mark.asyncio


async def test_retry_does_not_apply_the_previous_attempts_late_failure(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    from notification.models import NotificationDelivery
    from notification.tasks.normalize import normalize_pending
    from tests.test_normalize import _capture_event

    delivery = await _make_sent_delivery(
        session, tenant_a, status="failed", provider_message_id="previous-attempt"
    )
    proof = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.delivery.retry"]
    )
    response = await client.post(
        f"/v1/deliveries/{delivery.id}/retry", headers={**proof, "Idempotency-Key": "new-cycle"}
    )
    assert response.status_code == 200
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="previous-attempt",
        event_type="Bounce",
        external_event_key="late-bounce",
    )
    await normalize_pending(session)
    await session.commit()
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id, populate_existing=True)
        assert row is not None and row.status == "pending" and row.provider_message_id is None


async def _variant(client: httpx.AsyncClient, tenant: uuid.UUID, channel: str) -> tuple[str, str]:
    headers = actor_headers(
        tenant_id=tenant, user_id=uuid7(), permissions=["notification.template.manage"]
    )
    template = await client.post(
        "/v1/templates",
        headers=headers,
        json={
            "company_id": str(uuid7()),
            "key": uuid7().hex,
            "event_key": "review.event",
            "category": "transactional",
            "default_locale": "en",
        },
    )
    assert template.status_code == 201
    variant = await client.post(
        f"/v1/templates/{template.json()['id']}/variants",
        headers=headers,
        json={"channel": channel, "locale": "en"},
    )
    assert variant.status_code == 201
    version = await client.post(
        f"/v1/variants/{variant.json()['id']}/versions",
        headers=headers,
        json={"body_text": "Hello"},
    )
    assert version.status_code == 201
    return str(variant.json()["id"]), str(version.json()["id"])


@pytest.mark.parametrize("foreign_tenant", [False, True])
async def test_activation_rejects_foreign_variant_version(
    client: httpx.AsyncClient, tenant_a: uuid.UUID, tenant_b: uuid.UUID, foreign_tenant: bool
) -> None:
    variant, _ = await _variant(client, tenant_a, "sms")
    _, version = await _variant(client, tenant_b if foreign_tenant else tenant_a, "email")
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.template.manage"]
    )
    response = await client.post(
        f"/v1/variants/{variant}/activations",
        headers=headers,
        json={"template_version_id": version, "valid_from": "2026-01-01T00:00:00Z"},
    )
    assert response.status_code == 422


async def test_provider_mutation_has_redacted_actor_attributed_audit(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    from billing_platform.db.platform_models import Outbox

    user = uuid7()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user, permissions=["notification.provider.manage"]
    )
    created = await client.post(
        "/v1/provider-accounts",
        headers=headers,
        json={
            "key": "audit",
            "callback_key": "a" * 43,
            "channel": "sms",
            "provider_key": "twilio",
            "display_name": "Private display",
            "credential_ref": "env:PRIVATE",
            "callback_secret_ref": "env:VERIFY",
        },
    )
    assert created.status_code == 201
    provider_id = created.json()["id"]
    response = await client.patch(
        f"/v1/provider-accounts/{provider_id}",
        headers=headers,
        json={"display_name": "Another private display"},
    )
    assert response.status_code == 200
    with tenant_scope(tenant_a):
        rows = list(
            (
                await session.scalars(
                    select(Outbox).where(Outbox.aggregate_id == uuid.UUID(provider_id))
                )
            ).all()
        )
    audits = [row for row in rows if "action" in row.payload]
    assert len(audits) == 2
    assert all(row.payload["actor_user_id"] == str(user) for row in audits)
    assert "private display" not in str([row.payload for row in audits]).lower()
    assert "env:PRIVATE" not in str([row.payload for row in audits])


async def test_invalid_backoff_range_is_rejected() -> None:
    from notification.api.schemas_mgmt import RoutingRuleCreate

    with pytest.raises(ValidationError):
        RoutingRuleCreate(
            company_id=uuid7(),
            event_key="event",
            category="transactional",
            channel="sms",
            provider_account_id=uuid7(),
            sender_identity_id=uuid7(),
            priority=1,
            weight=1,
            max_attempts=3,
            timeout_seconds=1,
            initial_backoff_seconds=60,
            max_backoff_seconds=5,
        )


async def test_dispatch_honors_route_timeout_without_blind_retry(
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from notification.models import RoutingRule

    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        rule = await session.get(RoutingRule, delivery.routing_rule_id)
        assert rule is not None
        rule.timeout_seconds = 1
        await session.commit()

    class SlowProvider:
        async def send(self, command: SendCommand) -> SendResult:
            await asyncio.sleep(1.2)
            return SendResult("accepted", "late")

    result = await Dispatcher(factory, {delivery.provider_account_id: SlowProvider()}).dispatch(
        tenant_a, delivery.id, SendCommand("test@example.test", "sender", "body", None, "slow")
    )
    assert result.outcome == "unknown"
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
    assert delivery.status == "sending"


async def test_manual_retries_preserve_attempt_history_and_can_repeat(
    client: httpx.AsyncClient,
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    delivery = await _make_sent_delivery(session, tenant_a, status="pending")

    class RejectingProvider:
        async def send(self, command: SendCommand) -> SendResult:
            return SendResult("permanent_failure", None, error_code="rejected")

    dispatcher = Dispatcher(factory, {delivery.provider_account_id: RejectingProvider()})
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.delivery.retry"]
    )
    for expected_attempt in range(1, 4):
        await dispatcher.dispatch(
            tenant_a,
            delivery.id,
            SendCommand(
                "test@example.test", "sender", "body", None, f"{delivery.id}:{expected_attempt}"
            ),
        )
        response = await client.post(
            f"/v1/deliveries/{delivery.id}/retry",
            headers={**headers, "Idempotency-Key": uuid7().hex},
        )
        assert response.status_code == 200
        assert response.json()["attempt_count"] == expected_attempt
    with tenant_scope(tenant_a):
        attempts = list(
            (
                await session.scalars(
                    select(DeliveryAttempt).order_by(DeliveryAttempt.attempt_number)
                )
            ).all()
        )
    assert [attempt.attempt_number for attempt in attempts] == [1, 2, 3]


@pytest.mark.parametrize(
    "category,expected", [("transactional", "suppressed"), ("security", "accepted")]
)
async def test_dispatch_rechecks_changed_preference(
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    category: str,
    expected: str,
) -> None:
    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        endpoint = await session.get(RecipientEndpoint, delivery.recipient_endpoint_id)
        request = await session.get(NotificationRequest, delivery.request_id)
        assert endpoint is not None and request is not None
        request.category = category
        session.add(
            NotificationPreference(
                id=uuid7(),
                tenant_id=tenant_a,
                subject_type=endpoint.subject_type,
                subject_id=endpoint.subject_id,
                event_key=request.event_key,
                channel=delivery.channel,
                is_enabled=False,
                source_version=1,
                source_updated_at=NOW,
                projected_at=NOW,
            )
        )
        await session.commit()
    calls = []

    class RecordingProvider:
        async def send(self, command: SendCommand) -> SendResult:
            calls.append(command)
            return SendResult("accepted", "recorded")

    dispatcher = Dispatcher(factory, {delivery.provider_account_id: RecordingProvider()})
    await dispatcher.dispatch(
        tenant_a, delivery.id, SendCommand("test@example.test", "sender", "body", None, "next")
    )
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
    assert delivery.status == expected
    assert len(calls) == (1 if category == "security" else 0)


@pytest.mark.parametrize("problem", ["destination", "body", "sender", "key"])
async def test_permanent_preflight_failure_leaves_dispatch_queue(
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    problem: str,
) -> None:
    from notification.models import NotificationContent, SenderIdentity

    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        endpoint = await session.get(RecipientEndpoint, delivery.recipient_endpoint_id)
        content = await session.get(NotificationContent, delivery.id)
        sender = await session.get(SenderIdentity, delivery.sender_identity_id)
        assert endpoint is not None and content is not None and sender is not None
        endpoint.destination_ciphertext = CIPHER.encrypt(
            b"test@example.test", nonce=b"n" * 12, associated_data=endpoint.id.bytes
        )
        if problem == "destination":
            endpoint.destination_ciphertext = None
        elif problem == "body":
            content.body_text_ciphertext = None
        elif problem == "sender":
            sender.verification_status = "unverified"
        else:
            content.encryption_key_ref = "unavailable:key"
        await session.commit()
    result = await Dispatcher(factory, {}).dispatch_stored(
        tenant_a, delivery.id, cipher=CIPHER, key_ref=KEY_REF
    )
    assert result.outcome == "permanent_failure"
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
    assert delivery.status == "failed"
    assert delivery.attempt_count == 0


@pytest.mark.parametrize(
    "change",
    [
        {"display_name": None},
        {"credential_ref": None},
        {"status": None},
        {"status": "arbitrary"},
        {"callback_secret_ref": None},
    ],
)
async def test_provider_patch_rejects_invalid_configuration(
    client: httpx.AsyncClient,
    tenant_a: uuid.UUID,
    change: dict[str, object],
) -> None:
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.provider.manage"]
    )
    created = await client.post(
        "/v1/provider-accounts",
        headers=headers,
        json={
            "key": "review",
            "callback_key": "r" * 43,
            "channel": "sms",
            "provider_key": "twilio",
            "display_name": "Review",
            "credential_ref": "env:REVIEW",
            "callback_secret_ref": "env:VERIFY",
        },
    )
    assert created.status_code == 201
    response = await client.patch(
        f"/v1/provider-accounts/{created.json()['id']}", headers=headers, json=change
    )
    assert response.status_code == 422
