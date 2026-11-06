"""Confirmed outbox delivery and transactional inbox consumption.

Broker adapters supply publishing and acknowledgement. No acknowledgement is
permitted until consume_once returns (after commit). A retry uses the original
message ID; handlers write domain state and audit/outbox in the supplied session.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db.platform_models import Outbox, ProcessedMessage
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.idempotency import canonical_json
from billing_platform.messages import MessageEnvelope

# Registry size is independent of per-transaction batch size and consumer prefetch.
MAX_EVENT_TYPES = 1024


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    message_id: uuid.UUID
    routing_key: str
    body: bytes


@dataclass(frozen=True, slots=True)
class PublishResult:
    confirmed: int
    deferred: int


async def publish_batch(
    factory: async_sessionmaker[AsyncSession],
    publish: Callable[[OutgoingMessage], Awaitable[bool]],
    *,
    limit: int = 50,
    timeout_seconds: int = 5,
    event_types: frozenset[str] | None = None,
    maximum_attempts: int | None = None,
    retry_cap_seconds: int = 3600,
    occurred_after: dt.datetime | None = None,
) -> PublishResult:
    """Lock a bounded batch; mark published only after positive confirmation.

    The adapter must use durable messages, publisher confirms and mandatory
    routing. This worker reads exempt infrastructure rows across tenants. It
    never performs a remote call in a business transaction. A crash after broker
    confirmation may republish the same ID; downstream inboxes deduplicate it.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("outbox batch limit must be between 1 and 100")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
        raise ValueError("invalid publish timeout")
    if maximum_attempts is not None and (
        type(maximum_attempts) is not int or not 1 <= maximum_attempts <= 32767
    ):
        raise ValueError("invalid maximum publish attempts")
    if type(retry_cap_seconds) is not int or not 1 <= retry_cap_seconds <= 3600:
        raise ValueError("invalid retry cap")
    if occurred_after is not None and occurred_after.tzinfo is None:
        raise ValueError("publication cutoff must include a timezone")
    if event_types is not None and (
        not 1 <= len(event_types) <= MAX_EVENT_TYPES
        or any(not re.fullmatch(r"[a-z][a-z0-9_.-]{0,119}", name) for name in event_types)
    ):
        raise ValueError("outbox routes must be explicit bounded event types")
    confirmed = deferred = 0
    async with factory() as db, db.begin():
        route_filter = () if event_types is None else (Outbox.event_type.in_(event_types),)
        attempts_filter = (
            () if maximum_attempts is None else (Outbox.attempt_count < maximum_attempts,)
        )
        cutoff_filter = () if occurred_after is None else (Outbox.occurred_at >= occurred_after,)
        rows = (
            await db.scalars(
                select(Outbox)
                .where(
                    Outbox.published_at.is_(None),
                    Outbox.available_at <= utcnow(),
                    *route_filter,
                    *attempts_filter,
                    *cutoff_filter,
                )
                .order_by(Outbox.available_at, Outbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            row.attempt_count = min(row.attempt_count + 1, 32767)
            try:
                body = canonical_json(
                    {
                        "message_id": str(row.message_id),
                        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
                        "event_type": row.event_type,
                        "schema_version": row.schema_version,
                        "occurred_at": row.occurred_at.isoformat(),
                        "trace_id": row.trace_id,
                        "payload": row.payload,
                    }
                )
                async with asyncio.timeout(timeout_seconds):
                    acknowledged = await publish(
                        OutgoingMessage(row.message_id, row.event_type, body)
                    )
                if acknowledged is not True:
                    raise RuntimeError("publisher did not confirm delivery")
            except Exception as exc:
                # Class only; broker exception messages may contain credentials.
                row.last_error = type(exc).__name__
                row.available_at = utcnow() + dt.timedelta(
                    seconds=min(retry_cap_seconds, 2 ** min(row.attempt_count, 12))
                )
                deferred += 1
            else:
                row.published_at = utcnow()
                row.last_error = None
                confirmed += 1
    return PublishResult(confirmed, deferred)


async def consume_once(
    factory: async_sessionmaker[AsyncSession],
    envelope: MessageEnvelope,
    handler: Callable[[AsyncSession, MessageEnvelope], Awaitable[None]],
    *,
    consumer_name: str,
) -> bool:
    """True for applied, False for already committed; both may be acknowledged.

    Validate broker source identity/contract before calling. MessageEnvelope is
    data validation, not authentication. The globally unique message ID and
    consumer name are the existing platform inbox key. A failed handler leaves
    no inbox marker and must not be acknowledged as successfully applied.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,119}", consumer_name):
        raise ValueError("invalid consumer name")
    if envelope.tenant_id.int == 0 or envelope.message_id.int == 0:
        raise ValueError("consumer requires non-nil tenant and message IDs")
    duplicate_error: IntegrityError | None = None
    with tenant_scope(envelope.tenant_id):
        async with factory() as db:
            async with db.begin():
                db.add(
                    ProcessedMessage(consumer_name=consumer_name, message_id=envelope.message_id)
                )
                try:
                    await db.flush()
                except IntegrityError as exc:
                    duplicate_error = exc
                    await db.rollback()
                else:
                    await handler(db, envelope)
            if duplicate_error is not None:
                # Only a conflict on this exact inbox key means duplicate.
                # Handler integrity errors never enter this branch.
                existing = await db.scalar(
                    select(ProcessedMessage.message_id).where(
                        ProcessedMessage.consumer_name == consumer_name,
                        ProcessedMessage.message_id == envelope.message_id,
                    )
                )
                if existing is None:
                    raise duplicate_error
                return False
    return True
