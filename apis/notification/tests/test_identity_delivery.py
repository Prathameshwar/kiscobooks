from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.messages import MessageEnvelope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.models import (
    NotificationContent,
    NotificationDelivery,
    NotificationPreference,
    NotificationRequest,
    RecipientEndpoint,
    TemplateVersion,
)
from notification.providers import SendCommand, SendResult
from notification.tasks.identity import DeliveryConfigurationUnavailableError, handle_identity
from tests.notif_seed import CIPHER, KEY, KEY_REF, seed_email_route


def invitation(tenant: uuid.UUID, company: uuid.UUID, subject: uuid.UUID) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=uuid.uuid4(),
        tenant_id=tenant,
        event_type="identity.invitation.requested",
        schema_version=1,
        occurred_at=utcnow(),
        payload={
            "invitation_id": str(uuid.uuid4()),
            "company_id": str(company),
            "user_id": str(subject),
            "email": "new-user@example.test",
            "locale": "en-IN",
            "invitation_url": "https://auth.test/accept?invitation=public-reference",
            "expires_at": (utcnow() + dt.timedelta(days=1)).isoformat(),
        },
    )


async def apply(db: AsyncSession, event: MessageEnvelope) -> None:
    await handle_identity(
        db,
        event,
        cipher=CIPHER,
        key_ref=KEY_REF,
        destination_key=KEY,
        auth_origin="https://auth.test",
    )


async def test_invitation_targets_signed_address_encrypts_dedupes_and_renders(
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, subject = uuid.uuid4(), uuid.uuid4()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="user.invited",
        category="security",
    )
    with tenant_scope(tenant_a):
        template = (await session.scalars(select(TemplateVersion))).one()
        template.subject_text = "Your invitation"
        template.body_text = "Accept securely: {{ invitation_url }}"
        await session.commit()
        event = invitation(tenant_a, company, subject)
        await apply(session, event)
        await session.commit()
        await apply(session, event)
        await session.commit()
        rows = list(await session.scalars(select(NotificationDelivery)))
        assert len(rows) == 1
        endpoint = await session.get(RecipientEndpoint, rows[0].recipient_endpoint_id)
        assert endpoint is not None and endpoint.destination_ciphertext is not None
        assert (
            CIPHER.decrypt(endpoint.destination_ciphertext, associated_data=endpoint.id.bytes)
            == b"new-user@example.test"
        )
        content = await session.get(NotificationContent, rows[0].id)
        assert content is not None and content.body_text_ciphertext
        assert b"https://auth.test/accept" in CIPHER.decrypt(
            content.body_text_ciphertext, associated_data=rows[0].id.bytes
        )
        request = (await session.scalars(select(NotificationRequest))).one()
        assert b"https://auth.test/accept" not in request.context_ciphertext
        assert "new-user@example.test" not in str(
            [e.payload for e in await session.scalars(select(Outbox))]
        )
    from notification.providers import SendResult
    from notification.tasks.dispatch import Dispatcher

    class CaptureProvider:
        async def send(self, command: SendCommand) -> SendResult:
            assert command.destination == "new-user@example.test"
            assert "https://auth.test/accept" in command.body
            return SendResult("accepted", "test-provider-message")

    dispatcher = Dispatcher(factory, {rows[0].provider_account_id: CaptureProvider()})
    result = await dispatcher.dispatch_stored(tenant_a, rows[0].id, cipher=CIPHER, key_ref=KEY_REF)
    assert result.outcome == "accepted"
    with tenant_scope(tenant_b):
        assert not list(await session.scalars(select(NotificationDelivery)))


async def test_missing_route_rolls_back_and_expired_invitation_is_not_sent(
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    event = invitation(tenant_a, uuid.uuid4(), uuid.uuid4())
    with tenant_scope(tenant_a):
        with pytest.raises(DeliveryConfigurationUnavailableError):
            await apply(session, event)
        await session.rollback()
        assert not list(await session.scalars(select(RecipientEndpoint)))
        event.payload["expires_at"] = (utcnow() - dt.timedelta(seconds=1)).isoformat()
        await apply(session, event)
        assert not list(await session.scalars(select(NotificationRequest)))


async def test_identity_preference_projection_uses_source_version(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    event = MessageEnvelope(
        message_id=uuid.uuid4(),
        tenant_id=tenant_a,
        schema_version=1,
        event_type="user_notification_preference.changed",
        occurred_at=utcnow(),
        payload={
            "subject_type": "user",
            "subject_id": str(uuid.uuid4()),
            "event_key": "invoice.posted",
            "channel": "email",
            "is_enabled": False,
            "source_version": 2,
            "source_updated_at": utcnow().isoformat(),
        },
    )
    with tenant_scope(tenant_a):
        await apply(session, event)
        event.payload.update(is_enabled=True, source_version=1)
        await apply(session, event)
        row = (await session.scalars(select(NotificationPreference))).one()
        assert row.source_version == 2 and row.is_enabled is False


async def test_template_bootstrap_is_idempotent_and_scoped(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from notification.models import NotificationTemplate
    from notification.tasks.invitation_template import install

    with tenant_scope(tenant_a):
        first = await install(session, tenant_a)
        assert await install(session, tenant_a) == first
        await session.commit()
        assert len(list(await session.scalars(select(NotificationTemplate)))) == 1
    with tenant_scope(tenant_b):
        assert not list(await session.scalars(select(NotificationTemplate)))


async def test_whatsapp_dispatch_resolves_bindings_and_parameters(
    session: AsyncSession, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    import hashlib

    from billing_platform.db.tenant_context import unfiltered
    from billing_platform.ids import uuid7

    from notification.models import (
        NotificationTemplate,
        ProviderAccount,
        ProviderTemplateBinding,
        RecipientEndpoint,
        RoutingRule,
        SenderIdentity,
        TemplateActivation,
        TemplateVariant,
        TemplateVersion,
    )
    from notification.providers import SendResult
    from notification.tasks.consume import handle_send_command
    from notification.tasks.dispatch import Dispatcher
    from tests.notif_seed import HMAC, NOW, envelope

    # Let's seed a WhatsApp route, template, recipient, variants, bindings
    provider, sender, template, variant, version = (uuid7() for _ in range(5))
    company, subject = uuid.uuid4(), uuid.uuid4()
    endpoint_id = uuid7()
    with unfiltered():
        session.add(
            ProviderAccount(
                id=provider,
                tenant_id=tenant_a,
                status="active",
                key="meta",
                callback_key="w" * 43,
                channel="whatsapp",
                provider_key="meta",
                display_name="Meta",
                credential_ref="env:META",
            )
        )
        session.add(
            NotificationTemplate(
                id=template,
                tenant_id=tenant_a,
                company_id=company,
                key="wa_inv",
                event_key="invoice.posted",
                category="transactional",
                default_locale="en-IN",
                variable_schema={},
            )
        )
        session.add(
            RecipientEndpoint(
                id=endpoint_id,
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=subject,
                channel="whatsapp",
                destination_hmac=HMAC,
                destination_masked="+1555***1111",
                destination_ciphertext=CIPHER.encrypt(
                    b"+15550001111", nonce=b"y" * 12, associated_data=endpoint_id.bytes
                ),
                locale="en-IN",
                timezone="Asia/Kolkata",
                verification_status="verified",
                health_status="healthy",
                source_version=1,
            )
        )
        await session.flush()
        session.add(
            SenderIdentity(
                id=sender,
                tenant_id=tenant_a,
                provider_account_id=provider,
                key="wa_num",
                sender_type="whatsapp",
                external_sender_id="15550002222",
                display_name="WhatsApp",
                verification_status="verified",
            )
        )
        session.add(
            TemplateVariant(
                id=variant,
                tenant_id=tenant_a,
                template_id=template,
                channel="whatsapp",
                locale="en-IN",
            )
        )
        await session.flush()
        session.add(
            TemplateVersion(
                id=version,
                tenant_id=tenant_a,
                template_variant_id=variant,
                version=1,
                body_text="Hi {{ name }}, your total is {{ amount }}.",
                channel_payload={"template_parameters": ["name", "amount"]},
                content_sha256=hashlib.sha256(b"wa_v1").digest(),
            )
        )
        await session.flush()
        session.add(
            TemplateActivation(
                id=uuid7(),
                tenant_id=tenant_a,
                template_variant_id=variant,
                template_version_id=version,
                valid_from=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            )
        )
        session.add(
            ProviderTemplateBinding(
                id=uuid7(),
                tenant_id=tenant_a,
                template_version_id=version,
                provider_account_id=provider,
                external_template_id="wa_tmpl_external",
                external_language="en",
                external_name="invoice",
                approval_status="approved",
                synced_at=NOW,
            )
        )
        session.add(
            RoutingRule(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=company,
                event_key="invoice.posted",
                category="transactional",
                channel="whatsapp",
                provider_account_id=provider,
                sender_identity_id=sender,
                priority=1,
                weight=1,
                max_attempts=3,
                timeout_seconds=10,
                initial_backoff_seconds=5,
                max_backoff_seconds=300,
            )
        )
        await session.commit()

    env = envelope(tenant_a, company, subject, channels=["whatsapp"])
    env.payload["variables"] = {"name": "Ada", "amount": "$45.00"}

    result = await handle_send_command(session, env, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()
    assert result.deliveries_created == 1
    assert result.outcomes == {"whatsapp": "send"}

    with tenant_scope(tenant_a):
        delivery = (await session.scalars(select(NotificationDelivery))).one()
        assert delivery.provider_template_binding_id is not None

    class CaptureProvider:
        async def send(self, command: SendCommand) -> SendResult:
            assert command.destination == "+15550001111"
            assert command.sender == "15550002222"
            assert command.provider_template_name == "invoice"
            assert command.template_language == "en"
            assert command.template_components == (
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Ada"},
                        {"type": "text", "text": "$45.00"},
                    ],
                },
            )
            return SendResult("accepted", "whatsapp-msg-id-123")

    dispatcher = Dispatcher(factory, {delivery.provider_account_id: CaptureProvider()})
    dispatch_res = await dispatcher.dispatch_stored(
        tenant_a, delivery.id, cipher=CIPHER, key_ref=KEY_REF
    )
    assert dispatch_res.outcome == "accepted"


async def test_retryable_provider_failure_schedules_backoff(
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from notification.providers import SendResult
    from notification.tasks.dispatch import Dispatcher

    company, subject = uuid.uuid4(), uuid.uuid4()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="user.invited",
        category="security",
    )
    with tenant_scope(tenant_a):
        template = (await session.scalars(select(TemplateVersion))).one()
        template.subject_text = "Your invitation"
        template.body_text = "Accept: {{ invitation_url }}"
        await session.commit()
        await apply(session, invitation(tenant_a, company, subject))
        await session.commit()
        delivery = (await session.scalars(select(NotificationDelivery))).one()
        delivery_id = delivery.id
        provider_id = delivery.provider_account_id

    class RetryProvider:
        async def send(self, command: SendCommand) -> SendResult:
            return SendResult("retryable_failure", None, 503, "throttled", 30)

    dispatcher = Dispatcher(factory, {provider_id: RetryProvider()})
    result = await dispatcher.dispatch_stored(
        tenant_a,
        delivery_id,
        cipher=CIPHER,
        key_ref=KEY_REF,
    )
    assert result.outcome == "retryable_failure"
    with tenant_scope(tenant_a):
        await session.refresh(delivery)
        assert delivery.status == "retry_wait"
        assert delivery.next_attempt_at is not None and delivery.next_attempt_at > utcnow()
        assert delivery.status_reason == "throttled"
