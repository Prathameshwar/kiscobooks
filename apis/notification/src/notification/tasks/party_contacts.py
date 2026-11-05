"""Project Accounting party contacts into purpose-scoped Notification endpoints."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import uuid
from typing import Literal, Self

from aio_pika.abc import AbstractIncomingMessage
from billing_platform.broker import (
    BrokerSource,
    confirmed_channel,
    declare_consumer_queue,
    receive_one,
)
from billing_platform.db import create_engine, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import ServiceKey
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import Settings
from notification.models import PartyEndpointCheckpoint, RecipientEndpoint
from notification.ownership import session_factory as notification_session_factory
from notification.security import AesGcmCipher, keyed_destination_hash

ROUTES = frozenset({"accounting.party_contact.snapshot"})
PURPOSES = ("GENERAL", "INVOICING", "PAYMENTS", "DELIVERY")
CHANNELS = ("email", "sms", "whatsapp")
logger = logging.getLogger(__name__)


class Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Literal["GENERAL", "INVOICING", "PAYMENTS", "DELIVERY"]
    channel: Literal["email", "sms", "whatsapp"]
    destination: str = Field(min_length=3, max_length=320)
    locale: str = Field(min_length=2, max_length=35)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    party_id: uuid.UUID
    source_version: int = Field(ge=1)
    destinations: list[Destination] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def distinct_destinations(self) -> Self:
        pairs = [(item.purpose, item.channel) for item in self.destinations]
        if len(pairs) != len(set(pairs)):
            raise ValueError("one selected destination per purpose and channel is required")
        return self


def _mask(channel: str, value: str) -> str:
    if channel == "email":
        local, _, domain = value.partition("@")
        return (local[:1] or "*") + "***@" + domain
    return value[:3] + "***" + value[-2:]


async def project_snapshot(
    db: AsyncSession,
    envelope: MessageEnvelope,
    *,
    cipher: AesGcmCipher,
    destination_key: bytes,
) -> None:
    if envelope.event_type != "accounting.party_contact.snapshot":
        raise ValidationFailedError("unsupported Accounting contact event")
    data = Snapshot.model_validate(envelope.payload)
    wanted: dict[tuple[str, str], Destination] = {
        (d.purpose, d.channel): d for d in data.destinations
    }
    now = utcnow()
    with tenant_scope(envelope.tenant_id):
        for purpose in PURPOSES:
            for channel in CHANNELS:
                checkpoint = await db.scalar(
                    select(PartyEndpointCheckpoint)
                    .where(
                        PartyEndpointCheckpoint.company_id == data.company_id,
                        PartyEndpointCheckpoint.party_id == data.party_id,
                        PartyEndpointCheckpoint.purpose == purpose,
                        PartyEndpointCheckpoint.channel == channel,
                    )
                    .with_for_update()
                )
                if checkpoint is not None and checkpoint.source_version >= data.source_version:
                    continue
                if checkpoint is None:
                    checkpoint = PartyEndpointCheckpoint(
                        id=uuid7(),
                        tenant_id=envelope.tenant_id,
                        company_id=data.company_id,
                        party_id=data.party_id,
                        purpose=purpose,
                        channel=channel,
                        source_version=data.source_version,
                        endpoint_id=None,
                    )
                    db.add(checkpoint)
                previous = (
                    await db.get(RecipientEndpoint, checkpoint.endpoint_id)
                    if checkpoint.endpoint_id is not None
                    else None
                )
                selected = wanted.get((purpose, channel))
                destination = selected.destination if selected else None
                digest = (
                    keyed_destination_hash(destination, destination_key)
                    if destination is not None
                    else None
                )
                if previous is not None and (
                    previous.destination_hmac != digest or previous.company_id != data.company_id
                ):
                    previous.is_active = False
                    previous.deactivated_at = now
                    previous.updated_at = now
                checkpoint.source_version = data.source_version
                if selected is None or digest is None or destination is None:
                    checkpoint.endpoint_id = None
                    continue
                subject_type = "party_" + purpose.lower()
                endpoint = await db.scalar(
                    select(RecipientEndpoint).where(
                        RecipientEndpoint.subject_type == subject_type,
                        RecipientEndpoint.subject_id == data.party_id,
                        RecipientEndpoint.company_id == data.company_id,
                        RecipientEndpoint.channel == channel,
                        RecipientEndpoint.destination_hmac == digest,
                    )
                )
                if endpoint is None:
                    endpoint = RecipientEndpoint(
                        id=uuid7(),
                        tenant_id=envelope.tenant_id,
                        subject_type=subject_type,
                        subject_id=data.party_id,
                        company_id=data.company_id,
                        channel=channel,
                        destination_hmac=digest,
                        destination_masked=_mask(channel, destination),
                        locale=selected.locale,
                        timezone="Asia/Kolkata",
                        verification_status="unverified",
                        health_status="healthy",
                        source_version=data.source_version,
                        is_active=True,
                    )
                    db.add(endpoint)
                else:
                    endpoint.source_version = data.source_version
                    endpoint.is_active = True
                    endpoint.deactivated_at = None
                    endpoint.updated_at = now
                    endpoint.locale = selected.locale
                endpoint.destination_ciphertext = cipher.encrypt(
                    destination.encode(),
                    nonce=os.urandom(12),
                    associated_data=endpoint.id.bytes,
                )
                checkpoint.endpoint_id = endpoint.id
        await db.flush()


async def receive_accounting(
    factory: async_sessionmaker[AsyncSession],
    message: AbstractIncomingMessage,
    *,
    settings: Settings,
) -> None:
    raw_key = settings.data_encryption_key.get_secret_value().encode()
    data_key = raw_key if len(raw_key) == 32 else hashlib.sha256(raw_key).digest()
    sources = {
        key_id: BrokerSource(
            ServiceKey(
                "accounting", "notification", ROUTES, source.secret.get_secret_value().encode()
            ),
            source.broker_user,
        )
        for key_id, source in settings.accounting_sources.items()
    }

    async def apply(db: AsyncSession, envelope: MessageEnvelope) -> None:
        data = Snapshot.model_validate(envelope.payload)
        source = settings.accounting_sources.get(str(message.headers.get("key_id", "")))
        if not any(
            grant.tenant_id == envelope.tenant_id and grant.company_id == data.company_id
            for grant in (source.scopes if source is not None else ())
        ):
            raise ValidationFailedError("party contact snapshot is outside the source scope")
        await project_snapshot(
            db,
            envelope,
            cipher=AesGcmCipher(data_key),
            destination_key=data_key,
        )

    await receive_one(
        factory,
        message,
        sources=sources,
        audience="notification",
        consumer_name="notification.accounting_contacts.v1",
        handler=apply,
    )


async def run(settings: Settings) -> None:
    if not settings.broker_url or not settings.accounting_sources:
        raise ValueError("Accounting contact broker sources are required")
    engine = create_engine(settings.database_url)
    factory = notification_session_factory(engine)
    try:
        while True:
            try:
                async with confirmed_channel(settings.broker_url) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name="platform.notification",
                        queue_name="notification.accounting_contacts.authenticated.v1",
                        dead_letter_exchange="platform.notification.dead",
                        routes=tuple(ROUTES),
                        prefetch=8,
                    )
                    async with queue.iterator() as messages:
                        async for message in messages:
                            await receive_accounting(factory, message, settings=settings)
            except Exception as exc:
                logger.warning("Accounting contact reconnect: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file)))  # type: ignore[call-arg]
