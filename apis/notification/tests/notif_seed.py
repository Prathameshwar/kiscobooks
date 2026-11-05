"""Shared seeding for send-pipeline tests: a complete email route + a send envelope.

No ORM relationships are declared between these tables, so inserts are flushed in
dependency order rather than left to the unit of work.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import (
    NotificationTemplate,
    ProviderAccount,
    RecipientEndpoint,
    RoutingRule,
    SenderIdentity,
    TemplateActivation,
    TemplateVariant,
    TemplateVersion,
)
from notification.security import AesGcmCipher

KEY = b"0123456789abcdef0123456789abcdef"  # 32 bytes
CIPHER = AesGcmCipher(KEY)
KEY_REF = "env:TEST"
NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
HMAC = b"d" * 32


async def seed_email_route(
    session: AsyncSession,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    subject: uuid.UUID,
    event_key: str = "invoice.posted",
    category: str = "transactional",
    subject_type: str = "user",
    endpoint_company_id: uuid.UUID | None = None,
) -> None:
    provider, sender, template, variant, version = (uuid7() for _ in range(5))
    with unfiltered():
        session.add(
            ProviderAccount(
                id=provider,
                tenant_id=tenant,
                status="active",
                key="ses",
                callback_key="c" * 43,
                channel="email",
                provider_key="ses",
                display_name="SES",
                credential_ref="env:SES",
            )
        )
        session.add(
            NotificationTemplate(
                id=template,
                tenant_id=tenant,
                company_id=company,
                key="inv",
                event_key=event_key,
                category=category,
                default_locale="en-IN",
                variable_schema={},
            )
        )
        session.add(
            RecipientEndpoint(
                id=uuid7(),
                tenant_id=tenant,
                subject_type=subject_type,
                subject_id=subject,
                company_id=endpoint_company_id or SCOPE_ALL,
                channel="email",
                destination_hmac=HMAC,
                destination_masked="a***@x.com",
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
                tenant_id=tenant,
                provider_account_id=provider,
                key="noreply",
                sender_type="email",
                external_sender_id="noreply@acme.example",
                display_name="Acme",
                verification_status="verified",
            )
        )
        session.add(
            TemplateVariant(
                id=variant, tenant_id=tenant, template_id=template, channel="email", locale="en-IN"
            )
        )
        await session.flush()
        session.add(
            TemplateVersion(
                id=version,
                tenant_id=tenant,
                template_variant_id=variant,
                version=1,
                subject_text="Invoice for {{ name }}",
                body_text="Hello {{ name }}",
                content_sha256=hashlib.sha256(b"v1").digest(),
            )
        )
        await session.flush()
        session.add(
            TemplateActivation(
                id=uuid7(),
                tenant_id=tenant,
                template_variant_id=variant,
                template_version_id=version,
                valid_from=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            )
        )
        session.add(
            RoutingRule(
                id=uuid7(),
                tenant_id=tenant,
                company_id=company,
                event_key=event_key,
                category=category,
                channel="email",
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


def envelope(
    tenant: uuid.UUID,
    company: uuid.UUID,
    subject: uuid.UUID,
    *,
    message_id: uuid.UUID | None = None,
    category: str = "transactional",
    event_key: str = "invoice.posted",
    channels: list[str] | None = None,
) -> MessageEnvelope:
    payload: dict[str, Any] = {
        "company_id": str(company),
        "source_service": "billing",
        "source_event_key": "invoice.posted",
        "event_key": event_key,
        "category": category,
        "aggregate_type": "invoice",
        "aggregate_id": str(uuid7()),
        "subject_type": "user",
        "subject_id": str(subject),
        "channels": channels or ["email"],
        "locale": "en-IN",
        "variables": {"name": "Ada"},
    }
    return MessageEnvelope(
        message_id=message_id or uuid7(),
        tenant_id=tenant,
        event_type="notification.send",
        schema_version=1,
        occurred_at=NOW,
        payload=payload,
    )
