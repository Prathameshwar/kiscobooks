"""Regression reproduction tests for findings B01-B08 and G01-G02."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.models import (
    NotificationDelivery,
    RecipientEndpoint,
    RoutingRule,
)
from notification.providers import SendCommand, SendResult
from notification.tasks.consume import handle_send_command
from notification.tasks.dispatch import Dispatcher
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route


@pytest.mark.asyncio
async def test_b03_scheduled_send_sets_status_scheduled_and_future_attempt(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, voucher, subject = uuid7(), uuid7(), uuid7()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="voucher.sales_order.issued",
        subject_type="party_general",
        endpoint_company_id=company,
    )
    scheduled_time = utcnow() + dt.timedelta(hours=2)
    base = envelope(tenant_a, company, subject, event_key="voucher.sales_order.issued")
    send = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(voucher),
                "source_version": 1,
                "scheduled_at": scheduled_time.isoformat(),
            },
        }
    )
    result = await handle_send_command(session, send, cipher=CIPHER, key_ref=KEY_REF)
    assert result.deliveries_created == 1
    await session.commit()

    with tenant_scope(tenant_a):
        delivery = await session.scalar(
            select(NotificationDelivery).where(NotificationDelivery.request_id == result.request_id)
        )
        assert delivery is not None
        # B03: Scheduled send must have status='scheduled' and next_attempt_at=scheduled_time
        assert delivery.status == "scheduled"
        assert delivery.next_attempt_at is not None
        assert abs((delivery.next_attempt_at - scheduled_time).total_seconds()) < 2


@pytest.mark.asyncio
async def test_b04_retry_exhaustion_transitions_to_failed(
    session: AsyncSession, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, subject = uuid.uuid4(), uuid.uuid4()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="voucher.sales_order.issued",
        subject_type="party_general",
        endpoint_company_id=company,
    )
    base = envelope(tenant_a, company, subject, event_key="voucher.sales_order.issued")
    send = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(uuid7()),
                "source_version": 1,
            },
        }
    )
    result = await handle_send_command(session, send, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()

    with tenant_scope(tenant_a):
        delivery = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
        endpoint = await session.get(RecipientEndpoint, delivery.recipient_endpoint_id)
        assert endpoint is not None
        endpoint.destination_ciphertext = CIPHER.encrypt(
            b"user@example.test", nonce=b"n" * 12, associated_data=endpoint.id.bytes
        )
        rule = (
            await session.scalars(
                select(RoutingRule).where(RoutingRule.id == delivery.routing_rule_id)
            )
        ).one()
        # Set max_attempts to 2
        rule.max_attempts = 2
        await session.commit()
        delivery_id = delivery.id
        provider_id = delivery.provider_account_id

    class FailingProvider:
        async def send(self, command: SendCommand) -> SendResult:
            return SendResult("retryable_failure", None, 503, "service_unavailable")

    dispatcher = Dispatcher(factory, {provider_id: FailingProvider()})

    # Attempt 1
    res1 = await dispatcher.dispatch_stored(tenant_a, delivery_id, cipher=CIPHER, key_ref=KEY_REF)
    assert res1.outcome == "retryable_failure"
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
        assert delivery.status == "retry_wait"
        assert delivery.attempt_count == 1
        # Manually reset next_attempt_at to now for immediate attempt 2
        delivery.next_attempt_at = utcnow() - dt.timedelta(seconds=1)
        await session.commit()

    # Attempt 2 -> Should hit max_attempts=2 and transition to failed!
    res2 = await dispatcher.dispatch_stored(tenant_a, delivery_id, cipher=CIPHER, key_ref=KEY_REF)
    assert res2.outcome == "retryable_failure"
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
        # B04 assertion: When max_attempts is reached, status must be failed!
        assert delivery.status == "failed"
        assert delivery.status_reason == "max_attempts_exceeded"
        assert delivery.failed_at is not None
        assert delivery.completed_at is not None


@pytest.mark.asyncio
async def test_b01_unviable_delivery_transitions_to_terminal_state(
    session: AsyncSession, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, subject = uuid.uuid4(), uuid.uuid4()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="voucher.sales_order.issued",
        subject_type="party_general",
        endpoint_company_id=company,
    )
    base = envelope(tenant_a, company, subject, event_key="voucher.sales_order.issued")
    send = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(uuid7()),
                "source_version": 1,
            },
        }
    )
    result = await handle_send_command(session, send, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()

    with tenant_scope(tenant_a):
        delivery = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
        # Deactivate the recipient endpoint
        endpoint = await session.get(RecipientEndpoint, delivery.recipient_endpoint_id)
        assert endpoint is not None
        endpoint.is_active = False
        await session.commit()
        delivery_id = delivery.id
        provider_id = delivery.provider_account_id

    class FailingProvider:
        async def send(self, command: SendCommand) -> SendResult:
            return SendResult("accepted", "mock_msg_id")

    dispatcher = Dispatcher(factory, {provider_id: FailingProvider()})
    res = await dispatcher.dispatch_stored(tenant_a, delivery_id, cipher=CIPHER, key_ref=KEY_REF)
    assert res.outcome == "permanent_failure"
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.status_reason == "route_or_endpoint_unavailable"
        assert delivery.completed_at is not None


@pytest.mark.asyncio
async def test_b08_whatsapp_zero_parameters_omits_components() -> None:
    import httpx

    from notification.providers.http import MetaWhatsAppAdapter

    captured_payload: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        import json

        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.123"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MetaWhatsAppAdapter(client, access_token="token")
        cmd = SendCommand(
            destination="+15551234567",
            sender="15550001111",
            body="plain text",
            subject=None,
            attempt_key="att1",
            provider_template_name="wa_hello",
            template_language="en",
            template_parameters=(),
        )
        res = await adapter.send(cmd)
        assert res.outcome == "accepted"
        assert "components" not in captured_payload["template"]


@pytest.mark.asyncio
async def test_b07_ses_sends_html_content() -> None:
    from notification.providers.ses import SesAdapter

    captured_kwargs: dict[str, Any] = {}

    class MockSesClient:
        async def send_email(self, **kwargs: Any) -> dict[str, Any]:
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return {"MessageId": "ses-msg-123"}

    adapter = SesAdapter(MockSesClient())
    cmd = SendCommand(
        destination="user@example.test",
        sender="noreply@example.test",
        body="Plain text body",
        subject="Invoice",
        attempt_key="att1",
        body_html="<h1>Invoice HTML</h1>",
    )
    res = await adapter.send(cmd)
    assert res.outcome == "accepted"
    assert "Html" in captured_kwargs["Content"]["Simple"]["Body"]
    assert captured_kwargs["Content"]["Simple"]["Body"]["Html"]["Data"] == "<h1>Invoice HTML</h1>"
    assert captured_kwargs["Content"]["Simple"]["Body"]["Text"]["Data"] == "Plain text body"


@pytest.mark.asyncio
async def test_b02_callback_payload_extraction_and_advancement(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    from notification.models import ProviderEvent
    from notification.providers.normalize import extract_callback_metadata
    from notification.tasks.normalize import normalize_pending

    # 1. Test Twilio SMS extraction
    twilio_body = b"MessageSid=SM999888&MessageStatus=delivered&To=%2B15551234"
    msg_id, ev_type, ext_key = extract_callback_metadata("sms", twilio_body)
    assert msg_id == "SM999888"
    assert ev_type == "delivered"
    assert ext_key != "SM999888"  # a receipt ID identifies an event, not its message

    # 2. Test Meta WhatsApp JSON extraction
    meta_body = (
        b'{"entry":[{"changes":[{"value":{"statuses":'
        b'[{"id":"wamid.ABC","status":"delivered"}]}}]}]}'
    )
    msg_id, ev_type, ext_key = extract_callback_metadata("whatsapp", meta_body)
    assert msg_id == "wamid.ABC"
    assert ev_type == "delivered"

    # 3. Test SES SNS JSON extraction
    ses_body = (
        b'{"Type":"Notification","Message":"{\\"eventType\\":'
        b'\\"Delivery\\",\\"mail\\":{\\"messageId\\":\\"ses-999\\"}}"}'
    )
    msg_id, ev_type, ext_key = extract_callback_metadata("email", ses_body)
    assert msg_id == "ses-999"
    assert ev_type == "delivery"

    # 4. Test normalizer advancement with body extraction
    company, voucher, subject = uuid7(), uuid7(), uuid7()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="voucher.sales_order.issued",
        subject_type="party_general",
        endpoint_company_id=company,
    )
    base = envelope(tenant_a, company, subject, event_key="voucher.sales_order.issued")
    send = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(voucher),
                "source_version": 1,
            },
        }
    )
    result = await handle_send_command(session, send, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()

    with tenant_scope(tenant_a):
        delivery = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
        delivery.status = "accepted"
        delivery.provider_message_id = "ses-999"
        provider_id = delivery.provider_account_id

        # Event with body ciphertext and None provider_message_id
        event = ProviderEvent(
            id=uuid7(),
            tenant_id=tenant_a,
            provider_account_id=provider_id,
            external_event_key="ext-123",
            provider_message_id=None,
            event_type="unknown",
            signature_verified=True,
            processing_status="pending",
            encryption_key_ref=KEY_REF,
            payload_ciphertext=CIPHER.encrypt(
                ses_body, nonce=b"n" * 12, associated_data=provider_id.bytes
            ),
            payload_sha256=b"s" * 32,
            received_at=utcnow(),
        )
        session.add(event)
        await session.commit()

        # Normalizer with cipher extracts ses-999 and updates delivery -> delivered!
        handled = await normalize_pending(session, cipher=CIPHER)
        assert handled == 1
        await session.refresh(delivery)
        assert delivery.status == "delivered"
        assert delivery.delivered_at is not None


@pytest.mark.asyncio
async def test_b06_routing_rule_compatibility_validation(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    from notification.models import ProviderAccount, SenderIdentity
    from tests.api_support import actor_headers

    manage = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.route.manage"]
    )
    email_provider_id = uuid7()
    sms_provider_id = uuid7()
    email_sender_id = uuid7()

    with tenant_scope(tenant_a):
        session.add(
            ProviderAccount(
                id=email_provider_id,
                tenant_id=tenant_a,
                status="active",
                key="ses_prov",
                callback_key="c1" * 20,
                channel="email",
                provider_key="ses",
                display_name="SES",
                credential_ref="env:SES",
            )
        )
        session.add(
            ProviderAccount(
                id=sms_provider_id,
                tenant_id=tenant_a,
                status="active",
                key="twilio_prov",
                callback_key="c2" * 20,
                channel="sms",
                provider_key="twilio",
                display_name="Twilio",
                credential_ref="env:TWILIO",
            )
        )
        session.add(
            SenderIdentity(
                id=email_sender_id,
                tenant_id=tenant_a,
                provider_account_id=email_provider_id,
                key="sales_mail",
                sender_type="email_address",
                external_sender_id="sales@example.test",
                display_name="Sales",
                verification_status="verified",
            )
        )
        await session.commit()

    # 1. Invalid category rejected (422)
    bad_cat = await client.post(
        "/v1/routing-rules",
        json={
            "company_id": str(uuid7()),
            "event_key": "voucher.sales_order.issued",
            "category": "invalid_category",
            "channel": "email",
            "provider_account_id": str(email_provider_id),
            "sender_identity_id": str(email_sender_id),
            "priority": 1,
            "weight": 1,
            "max_attempts": 3,
            "timeout_seconds": 10,
            "initial_backoff_seconds": 5,
            "max_backoff_seconds": 300,
        },
        headers=manage,
    )
    assert bad_cat.status_code == 422

    # 2. Channel mismatch (SMS provider on email rule) rejected (422)
    mismatched_channel = await client.post(
        "/v1/routing-rules",
        json={
            "company_id": str(uuid7()),
            "event_key": "voucher.sales_order.issued",
            "category": "transactional",
            "channel": "email",
            "provider_account_id": str(sms_provider_id),
            "sender_identity_id": str(email_sender_id),
            "priority": 1,
            "weight": 1,
            "max_attempts": 3,
            "timeout_seconds": 10,
            "initial_backoff_seconds": 5,
            "max_backoff_seconds": 300,
        },
        headers=manage,
    )
    assert mismatched_channel.status_code == 422

    # 3. Valid rule succeeds (201)
    valid_rule = await client.post(
        "/v1/routing-rules",
        json={
            "company_id": str(uuid7()),
            "event_key": "voucher.sales_order.issued",
            "category": "transactional",
            "channel": "email",
            "provider_account_id": str(email_provider_id),
            "sender_identity_id": str(email_sender_id),
            "priority": 1,
            "weight": 1,
            "max_attempts": 3,
            "timeout_seconds": 10,
            "initial_backoff_seconds": 5,
            "max_backoff_seconds": 300,
        },
        headers=manage,
    )
    assert valid_rule.status_code == 201


@pytest.mark.asyncio
async def test_g02_manual_delivery_retry_api(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    from tests.api_support import actor_headers

    company, voucher, subject = uuid7(), uuid7(), uuid7()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="voucher.sales_order.issued",
        subject_type="party_general",
        endpoint_company_id=company,
    )
    base = envelope(tenant_a, company, subject, event_key="voucher.sales_order.issued")
    send = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(voucher),
                "source_version": 1,
            },
        }
    )
    result = await handle_send_command(session, send, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()

    with tenant_scope(tenant_a):
        delivery = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
        delivery_id = delivery.id
        # Delivery is currently "pending"

    retry_headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.delivery.retry"]
    )

    # Retrying a "pending" delivery should return 409 Conflict
    conflict_res = await client.post(
        f"/v1/deliveries/{delivery_id}/retry",
        headers={**retry_headers, "Idempotency-Key": uuid7().hex},
    )
    assert conflict_res.status_code == 409

    # Transition delivery to failed
    with tenant_scope(tenant_a):
        delivery.status = "failed"
        delivery.status_reason = "provider_error"
        delivery.failed_at = utcnow()
        delivery.completed_at = utcnow()
        await session.commit()

    # Now retry should succeed with 200 OK and reset status to pending
    success_res = await client.post(
        f"/v1/deliveries/{delivery_id}/retry",
        headers={**retry_headers, "Idempotency-Key": uuid7().hex},
    )
    assert success_res.status_code == 200
    data = success_res.json()
    assert data["status"] == "pending"
    assert data["status_reason"] == "manual_retry"
    assert data["attempt_count"] == 0

    with tenant_scope(tenant_a):
        await session.refresh(delivery)
        assert delivery.status == "pending"
        assert delivery.status_reason == "manual_retry"
        assert delivery.attempt_count == 0
        assert delivery.failed_at is None
        assert delivery.completed_at is None
