from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.models import DeliveryAttempt, NotificationDelivery, ProviderAccount
from notification.providers import SendCommand, SendResult
from notification.security import AesGcmCipher
from notification.tasks.dispatch import Dispatcher
from notification.tasks.normalize import normalize_pending
from tests.api_support import actor_headers
from tests.sns_fixture import TOPIC
from tests.sns_fixture import envelope as sns_envelope
from tests.test_normalize import _make_sent_delivery


@pytest.mark.parametrize(
    "outcome,message_id",
    [
        ("unknown", None),
        ("accepted", "contradictory-id"),
        ("permanent_failure", None),
        ("retryable_failure", None),
    ],
)
async def test_signed_receipt_recovers_unknown_send_before_finalization(
    outcome: str,
    message_id: str | None,
    client: httpx.AsyncClient,
    app: Any,
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        delivery.provider_message_id = None
        account = await session.get(ProviderAccount, delivery.provider_account_id)
        assert account is not None
        account.capabilities = {"sns_topic_arn": TOPIC}
        callback = account.callback_key
        await session.commit()
    key = f"{delivery.id}:1"

    class Provider:
        async def send(self, command: SendCommand) -> SendResult:
            body = json.dumps(
                {
                    "eventType": "Delivery",
                    "mail": {
                        "messageId": "signed-recovery-id",
                        "tags": {"attempt_key": [key.replace(":", "_")]},
                    },
                }
            ).encode()
            captured = await client.post(
                f"/v1/callbacks/email/{callback}", content=sns_envelope(body)
            )
            assert captured.status_code == 202
            async with factory() as db:
                assert await normalize_pending(db, cipher=AesGcmCipher(app.state.data_key)) == 1
                await db.commit()
            return SendResult(outcome, message_id, error_code="ambiguous_transport")

    dispatcher = Dispatcher(factory, {delivery.provider_account_id: Provider()})
    await dispatcher.dispatch(
        tenant_a, delivery.id, SendCommand("destination", "sender", "body", None, key)
    )
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id, populate_existing=True)
        attempt = (await session.scalars(select(DeliveryAttempt))).one()
        assert row is not None and row.status == "delivered" and row.status_reason is None
        assert row.provider_message_id == attempt.provider_message_id == "signed-recovery-id"
        assert row.attempt_count == 1
        assert attempt.outcome == "unknown"
        if outcome != "unknown":
            assert attempt.provider_error_code == "provider_result_conflicts_with_receipt"
    proof = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.delivery.read"]
    )
    inbox = await client.get("/v1/provider-events", headers=proof)
    assert inbox.status_code == 200 and len(inbox.json()["items"]) == 1
    receipt = inbox.json()["items"][0]
    assert receipt["attempt_key"] == key and receipt["delivery_id"] == str(delivery.id)
    assert "payload_ciphertext" not in receipt and "destination" not in receipt
    assert (
        await client.get(f"/v1/provider-events/{receipt['id']}", headers=proof)
    ).status_code == 200
    assert (await client.get("/v1/provider-events")).status_code == 401
    other = actor_headers(
        tenant_id=tenant_b, user_id=uuid7(), permissions=["notification.delivery.read"]
    )
    assert (await client.get("/v1/provider-events", headers=other)).json()["items"] == []
    assert (
        await client.get(f"/v1/provider-events/{receipt['id']}", headers=other)
    ).status_code == 404
    denied = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.provider.read"]
    )
    assert (await client.get("/v1/provider-events", headers=denied)).status_code == 403


async def test_conflicting_native_identity_does_not_poison_attempt(session, tenant_a):
    from billing_platform.db.types import utcnow

    from notification.models import ProviderEvent

    delivery = await _make_sent_delivery(
        session, tenant_a, status="sending", provider_message_id="response-proof"
    )
    with tenant_scope(tenant_a):
        delivery.attempt_count = 1
        attempt = DeliveryAttempt(
            tenant_id=tenant_a,
            delivery_id=delivery.id,
            attempt_number=1,
            provider_account_id=delivery.provider_account_id,
            sender_identity_id=delivery.sender_identity_id,
            attempt_key=f"{delivery.id}:1",
            started_at=utcnow(),
            outcome="in_progress",
            request_sha256=b"x" * 32,
        )
        event = ProviderEvent(
            tenant_id=tenant_a,
            provider_account_id=delivery.provider_account_id,
            external_event_key="conflicting-native-proof",
            attempt_key=attempt.attempt_key,
            provider_message_id="different-proof",
            event_type="Delivery",
            signature_verified=True,
            received_at=utcnow(),
            payload_sha256=b"x" * 32,
            encryption_key_ref="test",
            processing_status="pending",
        )
        session.add_all([attempt, event])
        await session.commit()
    assert await normalize_pending(session) == 1
    await session.commit()
    with tenant_scope(tenant_a):
        await session.refresh(attempt)
        await session.refresh(event)
        await session.refresh(delivery)
        assert attempt.provider_message_id is None
        assert event.processing_status == "unmatched" and event.delivery_id is None
        assert delivery.provider_message_id == "response-proof" and delivery.status == "sending"
