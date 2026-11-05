from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import secrets
import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import ServiceKey, sign_service_body
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import PlatformSource, Settings
from notification.domain.catalogue import definition
from notification.models import (
    ChannelSetting,
    NotificationRequest,
    NotificationSpace,
    NotificationTemplate,
    RecipientEndpoint,
    UseCaseBinding,
)
from notification.ownership import space_scope
from notification.security import AesGcmCipher
from notification.tasks.platform import EVENT, receive_platform
from tests.notif_seed import seed_email_route


def test_tenant_administrator_ready_has_password_free_email_contract():
    case = definition("tenant.administrator.ready", owner="platform")
    assert case.channels == ("email",)
    assert case.required_variables == ("sign_in_url", "username")
    assert "password" not in case.required_variables


class Incoming:
    def __init__(self, envelope: MessageEnvelope, secret: bytes) -> None:
        self.body = envelope.model_dump_json().encode()
        self.routing_key = self.type = envelope.event_type
        self.message_id = str(envelope.message_id)
        self.content_type = "application/json"
        self.user_id = "identity-platform"
        self.acked = self.rejected = False
        self.headers = {
            "key_id": "platform.current",
            "issuer": "identity",
            "audience": "notification",
            "signed_at": "1700000000",
            "signature": sign_service_body(
                ServiceKey("identity", "notification", frozenset({EVENT}), secret),
                key_id="platform.current",
                operation=EVENT,
                timestamp=1700000000,
                body=self.body,
            ),
        }

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, *, requeue: bool) -> None:
        self.rejected = not requeue


@pytest.mark.asyncio
async def test_pretenant_platform_delivery_is_encrypted_deduplicated_and_isolated(
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    space, subject, nil = uuid7(), uuid7(), uuid.UUID(int=0)
    signing_secret, ingress_secret = b"p" * 32, "e" * 32
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr("a" * 32),
        cursor_signing_secret=SecretStr("c" * 32),
        data_encryption_key=SecretStr("d" * 32),
        platform_owner_tenant_id=tenant_a,
        platform_space_id=space,
        platform_ingress_keys={"current": SecretStr(ingress_secret)},
        platform_sources={
            "platform.current": PlatformSource(
                owner_tenant_id=tenant_a,
                secret=SecretStr(signing_secret.decode()),
                broker_user="identity-platform",
            )
        },
    )
    with tenant_scope(tenant_a), space_scope(space):
        session.add(NotificationSpace(id=space, tenant_id=tenant_a, kind="platform"))
        session.add(ChannelSetting(tenant_id=tenant_a, channel="email", is_enabled=True))
        await seed_email_route(
            session,
            tenant=tenant_a,
            company=nil,
            subject=uuid7(),  # Unrelated to the new source-issued recipient reference.
            event_key="user.invited",
            category="security",
            subject_type="platform_recipient",
        )
        for endpoint in await session.scalars(select(RecipientEndpoint)):
            endpoint.is_active = False
        template = (await session.scalars(select(NotificationTemplate))).one()
        session.add(
            UseCaseBinding(
                tenant_id=tenant_a,
                company_id=nil,
                event_key="user.invited",
                trigger_key="identity.invitation.requested",
                channel="email",
                template_id=template.id,
                valid_from=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            )
        )
        await session.commit()
    message_id = uuid7()
    encrypted = AesGcmCipher(hashlib.sha256(ingress_secret.encode()).digest()).encrypt(
        json.dumps(
            {
                "destinations": {"email": "pretenant@example.invalid"},
                "variables": {"invitation_url": "https://auth.invalid/accept", "name": "New"},
            }
        ).encode(),
        nonce=secrets.token_bytes(12),
        associated_data=message_id.bytes + space.bytes + b"user.invited",
    )
    command = MessageEnvelope(
        message_id=message_id,
        tenant_id=tenant_a,
        event_type=EVENT,
        schema_version=1,
        occurred_at=dt.datetime.now(dt.UTC),
        payload={
            "space_id": str(space),
            "use_case": "user.invited",
            "trigger_key": "identity.invitation.requested",
            "recipient_ref": str(subject),
            "target_tenant_id": None,
            "channels": ["email"],
            "locale": "en-IN",
            "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).isoformat(),
            "key_id": "current",
            "encrypted_payload": base64.b64encode(encrypted).decode(),
        },
    )
    assert b"pretenant@example.invalid" not in command.model_dump_json().encode()
    for _ in range(2):
        incoming: Any = Incoming(command, signing_secret)
        await receive_platform(factory, incoming, settings=settings)
        assert incoming.acked and not incoming.rejected
    with tenant_scope(tenant_a):
        assert not list(await session.scalars(select(NotificationRequest)))
        with space_scope(space):
            rows = list(await session.scalars(select(NotificationRequest)))
            assert len(rows) == 1 and rows[0].target_tenant_id is None
    bad = command.model_copy(update={"message_id": uuid7(), "tenant_id": uuid7()})
    incoming = Incoming(bad, signing_secret)
    await receive_platform(factory, incoming, settings=settings)
    assert incoming.rejected and not incoming.acked
