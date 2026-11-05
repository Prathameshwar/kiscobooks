"""A late HTTP response belongs to its original manual-retry cycle."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select

from notification.models import DeliveryAttempt, NotificationDelivery, ProviderEvent
from notification.providers import SendCommand, SendResult
from notification.tasks.dispatch import Dispatcher
from notification.tasks.normalize import normalize_pending
from tests.api_support import actor_headers
from tests.test_normalize import _make_sent_delivery


@pytest.mark.parametrize("claim_next", [False, True])
async def test_old_http_finalization_cannot_overwrite_a_manual_retry(
    client, session, factory, tenant_a, claim_next
):
    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        delivery.provider_message_id = None
        await session.commit()
    proof = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.delivery.retry"]
    )

    class NextProvider:
        async def send(self, command):
            return SendResult("accepted", "new-cycle-message")

    class FirstProvider:
        async def send(self, command):
            # A verified provider rejection can precede completion of the send HTTP call.
            with tenant_scope(tenant_a):
                async with factory() as db:
                    db.add(
                        ProviderEvent(
                            tenant_id=tenant_a,
                            provider_account_id=delivery.provider_account_id,
                            external_event_key="early-reject",
                            attempt_key=command.attempt_key,
                            provider_message_id="old-cycle-message",
                            event_type="Reject",
                            signature_verified=True,
                            received_at=utcnow(),
                            payload_sha256=b"x" * 32,
                            encryption_key_ref="test",
                            processing_status="pending",
                        )
                    )
                    await db.commit()
            async with factory() as db:
                assert await normalize_pending(db) == 1
                await db.commit()
            retry = await client.post(
                f"/v1/deliveries/{delivery.id}/retry",
                headers={**proof, "Idempotency-Key": "next-cycle"},
            )
            assert retry.status_code == 200, retry.text
            if claim_next:
                await Dispatcher(factory, {delivery.provider_account_id: NextProvider()}).dispatch(
                    tenant_a, delivery.id, SendCommand("dest", "sender", "body", None, "next")
                )
            return SendResult("accepted", "old-cycle-message")

    await Dispatcher(factory, {delivery.provider_account_id: FirstProvider()}).dispatch(
        tenant_a, delivery.id, SendCommand("dest", "sender", "body", None, "first")
    )
    with tenant_scope(tenant_a):
        current = await session.get(NotificationDelivery, delivery.id, populate_existing=True)
        attempts = list(
            await session.scalars(select(DeliveryAttempt).order_by(DeliveryAttempt.attempt_number))
        )
        assert current.status == ("accepted" if claim_next else "pending")
        assert current.provider_message_id == ("new-cycle-message" if claim_next else None)
        assert current.attempt_count == (2 if claim_next else 1)
        assert attempts[0].provider_message_id == "old-cycle-message"
        assert attempts[0].completed_at is not None
