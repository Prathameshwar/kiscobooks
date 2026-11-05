"""Integration tests for the provider-event normalizer (docs/notification.md §2.2).

Uses the consumer to create a real delivery, simulates dispatch by stamping a
``provider_message_id``, captures a provider event, then normalizes — asserting the
delivery advances, a ``delivery_event`` is written, out-of-order events do not regress,
and unmatched events are parked.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import (
    DeliveryEvent,
    NotificationDelivery,
    NotificationRequest,
    ProviderAccount,
    ProviderEvent,
    RecipientEndpoint,
)
from notification.tasks.consume import handle_send_command
from notification.tasks.normalize import normalize_pending
from tests.notif_seed import CIPHER, KEY_REF, NOW, envelope, seed_email_route

pytestmark = pytest.mark.asyncio


async def test_complaint_after_read_suppresses_future_messages(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    from notification.models import Suppression

    delivery = await _make_sent_delivery(session, tenant_a, status="read")
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="PMID-1",
        event_type="Complaint",
        external_event_key="complaint-after-read",
    )
    assert await normalize_pending(session) == 1
    await session.commit()
    assert await normalize_pending(session) == 0
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id)
        assert row is not None and row.status == "read"
        suppression = (await session.scalars(select(Suppression))).one()
        assert suppression.reason == "complaint"


async def _make_sent_delivery(
    session: AsyncSession,
    tenant: uuid.UUID,
    *,
    status: str = "accepted",
    provider_message_id: str = "PMID-1",
) -> NotificationDelivery:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant, company=company, subject=subject)
    result = await handle_send_command(
        session, envelope(tenant, company, subject), cipher=CIPHER, key_ref=KEY_REF
    )
    await session.commit()
    with tenant_scope(tenant):
        delivery = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
        delivery.status = status
        delivery.provider_message_id = provider_message_id
        await session.commit()
    return delivery


async def _capture_event(
    session: AsyncSession,
    tenant: uuid.UUID,
    *,
    provider_account_id: uuid.UUID,
    provider_message_id: str | None,
    event_type: str,
    external_event_key: str,
) -> None:
    with unfiltered():
        session.add(
            ProviderEvent(
                id=uuid7(),
                tenant_id=tenant,
                provider_account_id=provider_account_id,
                external_event_key=external_event_key,
                provider_message_id=provider_message_id,
                event_type=event_type,
                signature_verified=True,
                received_at=NOW,
                payload_ciphertext=None,
                payload_sha256=b"0" * 32,
                encryption_key_ref=KEY_REF,
                processing_status="pending",
            )
        )
        await session.commit()


async def _count(session: AsyncSession, model: object, tenant: uuid.UUID) -> int:
    with tenant_scope(tenant):
        return int(await session.scalar(select(func.count(model.id))) or 0)  # type: ignore[attr-defined]


async def test_normalizer_advances_delivery(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    delivery = await _make_sent_delivery(session, tenant_a)
    baseline = await _count(session, DeliveryEvent, tenant_a)
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="PMID-1",
        event_type="Delivery",
        external_event_key="ext-1",
    )
    handled = await normalize_pending(session)
    await session.commit()
    assert handled == 1
    with tenant_scope(tenant_a):
        refreshed = await session.get(NotificationDelivery, delivery.id)
        event = (await session.scalars(select(ProviderEvent))).one()
    assert refreshed is not None
    assert refreshed.status == "delivered"
    assert refreshed.delivered_at is not None
    assert event.processing_status == "processed"
    assert event.delivery_id == delivery.id
    assert await _count(session, DeliveryEvent, tenant_a) == baseline + 1
    with tenant_scope(tenant_a):
        facts = list(
            await session.scalars(
                select(DeliveryEvent).where(
                    DeliveryEvent.delivery_id == delivery.id, DeliveryEvent.source == "email"
                )
            )
        )
        assert len(facts) == 1 and facts[0].from_status == "accepted"
        assert facts[0].to_status == "delivered"


async def test_out_of_order_event_does_not_regress(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _make_sent_delivery(session, tenant_a, status="read")
    baseline = await _count(session, DeliveryEvent, tenant_a)
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="PMID-1",
        event_type="Delivery",
        external_event_key="ext-2",
    )
    await normalize_pending(session)
    await session.commit()
    with tenant_scope(tenant_a):
        refreshed = await session.get(NotificationDelivery, delivery.id)
    assert refreshed is not None
    assert refreshed.status == "read"  # a late 'delivered' never regresses a read
    assert await _count(session, DeliveryEvent, tenant_a) == baseline


async def test_unmatched_event_is_parked(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    delivery = await _make_sent_delivery(session, tenant_a)
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="UNKNOWN",
        event_type="Delivery",
        external_event_key="ext-3",
    )
    await normalize_pending(session)
    await session.commit()
    with tenant_scope(tenant_a):
        event = (
            await session.scalars(
                select(ProviderEvent).where(ProviderEvent.external_event_key == "ext-3")
            )
        ).one()
    assert event.processing_status == "unmatched"


async def test_normalize_is_idempotent(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    delivery = await _make_sent_delivery(session, tenant_a)
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="PMID-1",
        event_type="Delivery",
        external_event_key="ext-4",
    )
    assert await normalize_pending(session) == 1
    await session.commit()
    assert await normalize_pending(session) == 0  # nothing pending on the second pass
    await session.commit()


async def test_whatsapp_batch_advances_every_message(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    first = await _make_sent_delivery(session, tenant_a, provider_message_id="WA-1")
    with tenant_scope(tenant_a):
        request = await session.get(NotificationRequest, first.request_id)
        endpoint = await session.get(RecipientEndpoint, first.recipient_endpoint_id)
        assert request is not None and endpoint is not None
        result = await handle_send_command(
            session,
            envelope(tenant_a, request.company_id, endpoint.subject_id),
            cipher=CIPHER,
            key_ref=KEY_REF,
        )
        second = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
        second.channel = first.channel = "whatsapp"
        second.status = "accepted"
        second.provider_message_id = "WA-2"
        provider = await session.get(ProviderAccount, first.provider_account_id)
        assert provider is not None
        provider.channel = "whatsapp"
        body = json.dumps(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "statuses": [
                                        {
                                            "id": "WA-1",
                                            "status": "delivered",
                                            "timestamp": "1780272000",
                                        },
                                        {"id": "WA-2", "status": "read", "timestamp": "1780272001"},
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ).encode()
        session.add(
            ProviderEvent(
                id=uuid7(),
                tenant_id=tenant_a,
                provider_account_id=provider.id,
                external_event_key="batch",
                provider_message_id="WA-1",
                event_type="delivered",
                signature_verified=True,
                received_at=NOW,
                payload_ciphertext=CIPHER.encrypt(
                    body, nonce=os.urandom(12), associated_data=provider.id.bytes
                ),
                payload_sha256=b"0" * 32,
                encryption_key_ref=KEY_REF,
                processing_status="pending",
            )
        )
        await session.commit()
    baseline = await _count(session, DeliveryEvent, tenant_a)
    assert await normalize_pending(session, cipher=CIPHER) == 1
    await session.commit()
    assert first.status == "delivered"
    assert second.status == "read"
    assert await _count(session, DeliveryEvent, tenant_a) == baseline + 2


async def test_corrupt_inbox_payload_is_quarantined(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _make_sent_delivery(session, tenant_a)
    await _capture_event(
        session,
        tenant_a,
        provider_account_id=delivery.provider_account_id,
        provider_message_id="PMID-1",
        event_type="Delivery",
        external_event_key="corrupt",
    )
    with tenant_scope(tenant_a):
        event = (await session.scalars(select(ProviderEvent))).one()
        event.payload_ciphertext = b"invalid encrypted payload"
        await session.commit()
    assert await normalize_pending(session, cipher=CIPHER) == 1
    await session.commit()
    assert event.processing_status == "error"
    assert delivery.status == "accepted"
