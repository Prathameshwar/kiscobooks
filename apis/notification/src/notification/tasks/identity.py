"""Authenticated Identity invitations and preference projection, one durable inbox."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import logging
import secrets
import uuid
from collections.abc import Mapping
from urllib.parse import urlsplit

from aio_pika.abc import AbstractIncomingMessage
from billing_platform.broker import (
    BrokerSource,
    confirmed_channel,
    declare_consumer_queue,
    receive_one,
)
from billing_platform.db import create_engine
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import ServiceKey
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import Settings
from notification.models import RecipientEndpoint
from notification.ownership import session_factory as notification_session_factory
from notification.security import AesGcmCipher, keyed_destination_hash
from notification.tasks.consume import handle_send_command
from notification.tasks.project import project_preference

ROUTES = frozenset({"identity.invitation.requested", "user_notification_preference.changed"})
logger = logging.getLogger(__name__)


class DeliveryConfigurationUnavailableError(PlatformError):
    code = "DELIVERY_CONFIGURATION_UNAVAILABLE"
    status_code = 503


class InvitationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    locale: str = Field(min_length=2, max_length=35)
    invitation_url: str = Field(max_length=2000)
    expires_at: dt.datetime


async def handle_identity(
    db: AsyncSession,
    envelope: MessageEnvelope,
    *,
    cipher: AesGcmCipher,
    key_ref: str,
    destination_key: bytes,
    auth_origin: str,
    content_retention_days: int = 90,
) -> None:
    if envelope.event_type == "user_notification_preference.changed":
        await project_preference(db, envelope)
        return
    if envelope.event_type != "identity.invitation.requested":
        raise ValidationFailedError("unsupported Identity contract")
    command = InvitationCommand.model_validate(envelope.payload)
    url, origin = urlsplit(command.invitation_url), urlsplit(auth_origin)
    if (
        url.scheme != "https"
        or not origin.hostname
        or url.netloc != origin.netloc
        or url.username
        or url.password
        or url.path != origin.path.rstrip("/") + "/accept"
        or url.fragment
        or command.expires_at.tzinfo is None
    ):
        raise ValidationFailedError("invalid invitation delivery target")
    if command.expires_at <= utcnow():
        return  # an expired invitation must never be sent after broker recovery
    destination = command.email.strip().casefold()
    digest = keyed_destination_hash(destination, destination_key)
    endpoint = await db.scalar(
        select(RecipientEndpoint).where(
            RecipientEndpoint.subject_type == "user",
            RecipientEndpoint.subject_id == command.user_id,
            RecipientEndpoint.channel == "email",
            RecipientEndpoint.destination_hmac == digest,
        )
    )
    if endpoint is None:
        endpoint = RecipientEndpoint(
            id=uuid7(),
            tenant_id=envelope.tenant_id,
            subject_type="user",
            subject_id=command.user_id,
            channel="email",
            destination_hmac=digest,
            destination_masked="***@" + destination.rsplit("@", 1)[1],
            locale=command.locale,
            timezone="UTC",
            verification_status="unverified",
            health_status="healthy",
            source_version=1,
        )
        endpoint.destination_ciphertext = cipher.encrypt(
            destination.encode(), nonce=secrets.token_bytes(12), associated_data=endpoint.id.bytes
        )
        db.add(endpoint)
        await db.flush()
    if not endpoint.is_active:
        raise DeliveryConfigurationUnavailableError("invitation endpoint is inactive")
    send = envelope.model_copy(
        update={
            "event_type": "notification.send",
            "payload": {
                "company_id": str(command.company_id),
                "source_service": "identity",
                "source_event_key": envelope.event_type,
                "event_key": "user.invited",
                "category": "security",
                "aggregate_type": "user_invitation",
                "aggregate_id": str(command.invitation_id),
                "subject_type": "user",
                "subject_id": str(command.user_id),
                "channels": ["email"],
                "locale": command.locale,
                "variables": {"invitation_url": command.invitation_url},
                "expires_at": command.expires_at.isoformat(),
            },
        }
    )
    result = await handle_send_command(
        db,
        send,
        cipher=cipher,
        key_ref=key_ref,
        endpoint_id=endpoint.id,
        content_retention_days=content_retention_days,
    )
    if not result.deduplicated and result.deliveries_created != 1:
        raise DeliveryConfigurationUnavailableError(
            "invitation template or email route is unavailable"
        )


async def receive_identity(
    factory: async_sessionmaker[AsyncSession],
    message: AbstractIncomingMessage,
    *,
    sources: Mapping[str, BrokerSource],
    cipher: AesGcmCipher,
    key_ref: str,
    destination_key: bytes,
    auth_origin: str,
    content_retention_days: int = 90,
) -> None:
    async def apply(db: AsyncSession, envelope: MessageEnvelope) -> None:
        await handle_identity(
            db,
            envelope,
            cipher=cipher,
            key_ref=key_ref,
            destination_key=destination_key,
            auth_origin=auth_origin,
            content_retention_days=content_retention_days,
        )

    await receive_one(
        factory,
        message,
        sources=sources,
        audience="notification",
        consumer_name="notification.identity.v1",
        handler=apply,
    )


async def run(settings: Settings) -> None:
    if (
        not settings.broker_url
        or not settings.identity_sources
        or not settings.identity_auth_origin
    ):
        raise ValueError("authenticated Identity delivery settings are required")
    raw_key = settings.data_encryption_key.get_secret_value().encode()
    data_key = raw_key if len(raw_key) == 32 else hashlib.sha256(raw_key).digest()
    sources = {
        key: BrokerSource(
            ServiceKey(
                "identity", "notification", ROUTES, value.secret.get_secret_value().encode()
            ),
            value.broker_user,
        )
        for key, value in settings.identity_sources.items()
    }
    engine = create_engine(settings.database_url)
    factory = notification_session_factory(engine)
    try:
        while True:
            try:
                async with confirmed_channel(settings.broker_url) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name="platform.notification",
                        queue_name="notification.identity.authenticated.v1",
                        dead_letter_exchange="platform.notification.dead",
                        routes=tuple(sorted(ROUTES)),
                        prefetch=1,
                        single_active_consumer=True,
                    )
                    async with queue.iterator() as messages:
                        async for message in messages:
                            await receive_identity(
                                factory,
                                message,
                                sources=sources,
                                cipher=AesGcmCipher(data_key),
                                key_ref=settings.data_encryption_key_ref,
                                destination_key=data_key,
                                auth_origin=settings.identity_auth_origin,
                                content_retention_days=settings.content_retention_days,
                            )
            except Exception as exc:
                logger.warning("Identity delivery reconnect: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file)))  # type: ignore[call-arg] # environment file
