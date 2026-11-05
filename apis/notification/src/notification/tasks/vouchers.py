"""Authenticated voucher send-command consumer with explicit company grants."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import uuid
from typing import Literal

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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import Settings
from notification.events import SendCommand
from notification.models import (
    DeliveryEvent,
    NotificationDelivery,
    NotificationRequest,
    VoucherSendState,
)
from notification.ownership import session_factory as notification_session_factory
from notification.security import AesGcmCipher
from notification.tasks.consume import handle_send_command

ROUTES = frozenset({"notification.send", "vouchers.voucher.notification_state"})
logger = logging.getLogger(__name__)


class TerminalState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    voucher_id: uuid.UUID
    source_version: int = Field(ge=1)
    status: Literal["CANCELLED", "DECLINED", "EXPIRED", "REVERSED"]


async def cancel_pending(
    db: AsyncSession,
    envelope: MessageEnvelope,
    state: TerminalState,
) -> None:
    now = utcnow()
    with tenant_scope(envelope.tenant_id):
        stored = await db.scalar(
            select(VoucherSendState)
            .where(
                VoucherSendState.company_id == state.company_id,
                VoucherSendState.voucher_id == state.voucher_id,
            )
            .with_for_update()
        )
        if stored is not None and stored.source_version >= state.source_version:
            state = TerminalState.model_validate(
                {
                    "company_id": stored.company_id,
                    "voucher_id": stored.voucher_id,
                    "source_version": stored.source_version,
                    "status": stored.status,
                }
            )
        elif stored is None:
            stored = VoucherSendState(
                id=uuid7(),
                tenant_id=envelope.tenant_id,
                company_id=state.company_id,
                voucher_id=state.voucher_id,
                source_version=state.source_version,
                status=state.status,
            )
            db.add(stored)
        else:
            stored.source_version = state.source_version
            stored.status = state.status
        deliveries = list(
            (
                await db.scalars(
                    select(NotificationDelivery)
                    .join(
                        NotificationRequest,
                        NotificationRequest.id == NotificationDelivery.request_id,
                    )
                    .where(
                        NotificationRequest.company_id == state.company_id,
                        NotificationRequest.aggregate_type == "voucher",
                        NotificationRequest.aggregate_id == state.voucher_id,
                        NotificationRequest.source_service == "vouchers",
                        NotificationDelivery.status.in_(["pending", "scheduled", "retry_wait"]),
                    )
                    .with_for_update()
                )
            ).all()
        )
        for delivery in deliveries:
            prior = delivery.status
            delivery.status = "cancelled"
            delivery.status_reason = "voucher_" + state.status.lower()
            delivery.updated_at = now
            db.add(
                DeliveryEvent(
                    id=uuid7(),
                    tenant_id=envelope.tenant_id,
                    delivery_id=delivery.id,
                    source="vouchers",
                    source_event_key=f"{envelope.message_id}:{delivery.id}",
                    from_status=prior,
                    to_status="cancelled",
                    reason_code=delivery.status_reason,
                    provider_occurred_at=None,
                    observed_at=now,
                    metadata_json=None,
                )
            )
        await db.flush()


async def receive_voucher(
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
                "vouchers", "notification", ROUTES, source.secret.get_secret_value().encode()
            ),
            source.broker_user,
        )
        for key_id, source in settings.voucher_sources.items()
    }

    async def apply(db: AsyncSession, envelope: MessageEnvelope) -> None:
        source = settings.voucher_sources.get(str(message.headers.get("key_id", "")))
        if envelope.event_type == "vouchers.voucher.notification_state":
            state = TerminalState.model_validate(envelope.payload)
            if not any(
                grant.tenant_id == envelope.tenant_id and grant.company_id == state.company_id
                for grant in (source.scopes if source is not None else ())
            ):
                raise ValidationFailedError("voucher state is outside the configured source scope")
            await cancel_pending(db, envelope, state)
            return
        command = SendCommand.model_validate(envelope.payload)
        if (
            command.source_service != "vouchers"
            or command.category != "transactional"
            or command.aggregate_type != "voucher"
            or command.source_version is None
            or not command.event_key.startswith("voucher.")
            or command.subject_type
            not in {"party_general", "party_invoicing", "party_payments", "party_delivery"}
            or command.source_event_key
            not in {
                "vouchers.voucher.share",
                "vouchers.voucher.issued",
                "vouchers.voucher.accepted",
                "vouchers.voucher.posted",
            }
            or not any(
                grant.tenant_id == envelope.tenant_id and grant.company_id == command.company_id
                for grant in (source.scopes if source is not None else ())
            )
        ):
            raise ValidationFailedError(
                "voucher send command is outside the configured source contract"
            )
        await handle_send_command(
            db,
            envelope,
            cipher=AesGcmCipher(data_key),
            key_ref=settings.data_encryption_key_ref,
            content_retention_days=settings.content_retention_days,
        )
        with tenant_scope(envelope.tenant_id):
            state = await db.scalar(
                select(VoucherSendState).where(
                    VoucherSendState.company_id == command.company_id,
                    VoucherSendState.voucher_id == command.aggregate_id,
                )
            )
        if state is not None:
            await cancel_pending(
                db,
                envelope,
                TerminalState.model_validate(
                    {
                        "company_id": state.company_id,
                        "voucher_id": state.voucher_id,
                        "source_version": state.source_version,
                        "status": state.status,
                    }
                ),
            )

    await receive_one(
        factory,
        message,
        sources=sources,
        audience="notification",
        consumer_name="notification.vouchers.v1",
        handler=apply,
    )


async def run(settings: Settings) -> None:
    if not settings.broker_url or not settings.voucher_sources:
        raise ValueError("voucher notification broker sources are required")
    engine = create_engine(settings.database_url)
    factory = notification_session_factory(engine)
    try:
        while True:
            try:
                async with confirmed_channel(settings.broker_url) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name="platform.notification",
                        queue_name="notification.vouchers.authenticated.v1",
                        dead_letter_exchange="platform.notification.dead",
                        routes=tuple(ROUTES),
                        prefetch=8,
                    )
                    async with queue.iterator() as messages:
                        async for message in messages:
                            await receive_voucher(factory, message, settings=settings)
            except Exception as exc:
                logger.warning("Voucher notification reconnect: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file)))  # type: ignore[call-arg]
