"""Authenticated, encrypted platform staff and pre-tenant delivery ingress."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import re
import secrets
import uuid
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from billing_platform.broker import (
    BrokerSource,
    confirmed_channel,
    declare_consumer_queue,
    receive_one,
)
from billing_platform.db import create_engine
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import ServiceKey
from cryptography.exceptions import InvalidTag
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import Settings
from notification.domain.catalogue import definition
from notification.models import NotificationRequest, NotificationSpace, RecipientEndpoint
from notification.ownership import session_factory, space_scope
from notification.security import AesGcmCipher, keyed_destination_hash
from notification.tasks.consume import handle_send_command

EVENT = "identity.platform_notification.requested"


class PlatformCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    space_id: uuid.UUID
    use_case: str = Field(max_length=120)
    trigger_key: str = Field(max_length=120)
    recipient_ref: uuid.UUID
    target_tenant_id: uuid.UUID | None = None
    channels: list[str] = Field(min_length=1, max_length=3)
    locale: str = Field(min_length=2, max_length=35)
    expires_at: AwareDatetime
    key_id: str = Field(max_length=120)
    encrypted_payload: str = Field(max_length=100000)


class PlatformContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destinations: dict[str, str] = Field(max_length=3)
    variables: dict[str, Any] = Field(max_length=100)


async def handle_platform(
    db: AsyncSession, envelope: MessageEnvelope, *, settings: Settings
) -> None:
    command = PlatformCommand.model_validate(envelope.payload)
    if (
        envelope.event_type != EVENT
        or envelope.tenant_id != settings.platform_owner_tenant_id
        or command.space_id != settings.platform_space_id
    ):
        raise ValidationFailedError("platform notification ownership does not match the source")
    use_case = definition(command.use_case, owner="platform")
    if command.trigger_key not in use_case.triggers or set(command.channels) - set(
        use_case.channels
    ):
        raise ValidationFailedError("unsupported platform delivery trigger/channel")
    if len(set(command.channels)) != len(command.channels):
        raise ValidationFailedError("duplicate platform channel")
    key = settings.platform_ingress_keys.get(command.key_id)
    if key is None:
        raise ValidationFailedError("unknown platform encryption key")
    try:
        cipher = AesGcmCipher(hashlib.sha256(key.get_secret_value().encode()).digest())
        plain = cipher.decrypt(
            base64.b64decode(command.encrypted_payload, validate=True),
            associated_data=envelope.message_id.bytes
            + command.space_id.bytes
            + command.use_case.encode(),
        )
        content = PlatformContent.model_validate_json(plain)
    except (InvalidTag, ValueError) as exc:
        raise ValidationFailedError("invalid encrypted platform payload") from exc
    if set(use_case.required_variables) - content.variables.keys():
        raise ValidationFailedError("required platform variables are missing")
    if set(content.destinations) != set(command.channels):
        raise ValidationFailedError("destinations do not match permitted channels")
    raw_key = settings.data_encryption_key.get_secret_value().encode()
    data_key = raw_key if len(raw_key) == 32 else hashlib.sha256(raw_key).digest()
    data_cipher = AesGcmCipher(data_key)
    with space_scope(command.space_id):
        root = await db.get(NotificationSpace, command.space_id, with_for_update=True)
        if root is None or root.kind != "platform":
            raise ValidationFailedError("platform notification space must be provisioned first")
        for channel, destination in content.destinations.items():
            destination = destination.strip()
            if channel == "email":
                if (
                    not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", destination)
                    or len(destination) > 320
                ):
                    raise ValidationFailedError("invalid email destination")
                destination = destination.casefold()
            elif not re.fullmatch(r"\+[1-9][0-9]{7,14}", destination):
                raise ValidationFailedError("phone destinations must use E.164")
            digest = keyed_destination_hash(destination, data_key)
            endpoint = await db.scalar(
                select(RecipientEndpoint).where(
                    RecipientEndpoint.subject_type == "platform_recipient",
                    RecipientEndpoint.subject_id == command.recipient_ref,
                    RecipientEndpoint.channel == channel,
                )
            )
            if endpoint is not None and endpoint.destination_hmac != digest:
                raise ValidationFailedError(
                    "recipient references bind one destination per channel; issue a new reference"
                )
            if endpoint is None:
                endpoint = RecipientEndpoint(
                    id=uuid7(),
                    tenant_id=envelope.tenant_id,
                    subject_type="platform_recipient",
                    subject_id=command.recipient_ref,
                    channel=channel,
                    destination_hmac=digest,
                    destination_masked="***@" + destination.rsplit("@", 1)[-1]
                    if channel == "email"
                    else "***" + destination[-4:],
                    locale=command.locale,
                    timezone="UTC",
                    verification_status="unverified",
                    health_status="healthy",
                    source_version=1,
                )
                endpoint.destination_ciphertext = data_cipher.encrypt(
                    destination.encode(),
                    nonce=secrets.token_bytes(12),
                    associated_data=endpoint.id.bytes,
                )
                db.add(endpoint)
                await db.flush()
        translated = envelope.model_copy(
            update={
                "event_type": "notification.send",
                "payload": {
                    "company_id": str(uuid.UUID(int=0)),
                    "source_service": "identity",
                    "source_event_key": command.trigger_key,
                    "event_key": command.use_case,
                    "category": use_case.category,
                    "aggregate_type": "platform_notification",
                    "aggregate_id": str(command.recipient_ref),
                    "subject_type": "platform_recipient",
                    "subject_id": str(command.recipient_ref),
                    "channels": command.channels,
                    "locale": command.locale,
                    "variables": content.variables,
                    "expires_at": command.expires_at.isoformat(),
                },
            }
        )
        result = await handle_send_command(
            db,
            translated,
            cipher=data_cipher,
            key_ref=settings.data_encryption_key_ref,
            content_retention_days=settings.content_retention_days,
        )
        request = await db.get(NotificationRequest, result.request_id)
        if request is not None:
            request.target_tenant_id = command.target_tenant_id
        await db.flush()


async def receive_platform(
    factory: async_sessionmaker[AsyncSession],
    message: AbstractIncomingMessage,
    *,
    settings: Settings,
) -> None:
    sources = {
        key: BrokerSource(
            ServiceKey(
                "identity",
                "notification",
                frozenset({EVENT}),
                value.secret.get_secret_value().encode(),
            ),
            value.broker_user,
        )
        for key, value in settings.platform_sources.items()
    }

    async def apply(db: AsyncSession, envelope: MessageEnvelope) -> None:
        source = settings.platform_sources.get(str(message.headers.get("key_id", "")))
        if source is None or source.owner_tenant_id != envelope.tenant_id:
            raise ValidationFailedError("platform source is outside its execution owner")
        await handle_platform(db, envelope, settings=settings)

    await receive_one(
        factory,
        message,
        sources=sources,
        audience="notification",
        consumer_name="notification.platform.v1",
        handler=apply,
    )


async def run(settings: Settings) -> None:
    if not settings.broker_url or not settings.platform_sources or not settings.platform_space_id:
        raise ValueError("platform source and ownership configuration is required")
    engine = create_engine(settings.database_url)
    try:
        factory = session_factory(engine)
        while True:
            try:
                async with confirmed_channel(settings.broker_url) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name="platform.notification",
                        queue_name="notification.platform.v1",
                        dead_letter_exchange="platform.notification.dead",
                        routes=(EVENT,),
                        prefetch=4,
                    )
                    async with queue.iterator() as messages:
                        async for message in messages:
                            await receive_platform(factory, message, settings=settings)
            except Exception:
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file)))  # type: ignore[call-arg] # environment settings
