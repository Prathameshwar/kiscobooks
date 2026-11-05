"""The audit-event ingestion consumer — the single hash-chain writer (docs/audit.md §4.2).

An emitting service stages an audit event on its outbox in the same transaction as the
business change (§2.1); RabbitMQ delivers it here as a ``MessageEnvelope``.
:func:`handle_event` dedupes on the outbox ``message_id``, assigns the tenant's next
``sequence``, computes ``prev_hash``/``row_hash``, and inserts one ``audit_event`` row.

**Single writer, in order.** ``consumer_prefetch`` is 1 so ``sequence`` and the chain link
are assigned without a race; scaling out would fork the chain and needs a per-tenant
sequencer first (§4.2). The handler is pure DB logic, tested against SQLite;
:func:`run_consumer` is the thin aio-pika transport bound to a live broker.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from billing_platform.broker import (
    BrokerSource,
    authenticated_envelope,
    confirmed_channel,
    declare_consumer_queue,
)
from billing_platform.db import create_engine, create_session_factory
from billing_platform.db.platform_models import ProcessedMessage
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.config import Settings
from audit.domain import hash_chain
from audit.domain.ingest import AuditEventPayload, event_fields
from audit.domain.source_contract import validate_source
from audit.models import AuditEvent


@dataclass(slots=True)
class IngestResult:
    event_id: uuid.UUID | None
    sequence: int | None = None
    deduplicated: bool = False


async def _chain_head(db: AsyncSession, tenant_id: uuid.UUID) -> tuple[int, bytes | None]:
    """The tenant's current ``(sequence, row_hash)``, or ``(0, None)`` for an empty chain.

    Runs inside ``tenant_scope`` so the session filter restricts the read to this tenant —
    the same mechanism that keeps one tenant's chain from ever reading another's head.
    """
    head = await db.scalar(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1))
    if head is None:
        return 0, None
    return head.sequence, head.row_hash


async def _already_ingested(db: AsyncSession, *, consumer_name: str, message_id: uuid.UUID) -> bool:
    existing = await db.scalar(
        select(ProcessedMessage.message_id).where(
            ProcessedMessage.consumer_name == consumer_name,
            ProcessedMessage.message_id == message_id,
        )
    )
    return existing is not None


async def handle_event(
    db: AsyncSession,
    envelope: MessageEnvelope,
    *,
    consumer_name: str,
    now: dt.datetime | None = None,
) -> IngestResult:
    """Ingest one audit event. Idempotent on ``envelope.message_id``.

    The caller owns the transaction (commit/rollback); this stages the ``audit_event`` row
    and its ``processed_message`` dedupe marker so a redelivery after commit is a no-op and
    a crash before commit leaves neither (invariant 10, docs/audit.md §2.2).
    """
    moment = now or utcnow()

    # Dedupe first, before touching the chain: an at-least-once redelivery must not append
    # a second row (§2.2). ``processed_message`` is infrastructure, outside the tenant filter.
    if await _already_ingested(db, consumer_name=consumer_name, message_id=envelope.message_id):
        return IngestResult(event_id=None, deduplicated=True)

    fields = event_fields(envelope, now=moment)

    with tenant_scope(envelope.tenant_id):
        last_sequence, prev_hash = await _chain_head(db, envelope.tenant_id)
        sequence = last_sequence + 1
        hashed: dict[str, Any] = {**fields, "sequence": sequence}
        row_hash = hash_chain.compute_row_hash(prev_hash=prev_hash, fields=hashed)

        event_id = uuid7()
        # Mass assignment is safe here: every value came through ``AuditEventPayload``
        # validation in ``event_fields`` (not raw request data), and the key set is the
        # module's own, not the caller's (CLAUDE.md §5.6).
        db.add(
            AuditEvent(
                id=event_id,
                sequence=sequence,
                prev_hash=prev_hash,
                row_hash=row_hash,
                **fields,
            )
        )
        db.add(
            ProcessedMessage(
                consumer_name=consumer_name,
                message_id=envelope.message_id,
                processed_at=moment,
            )
        )
        await db.flush()
        return IngestResult(event_id=event_id, sequence=sequence)


async def receive_audit(
    factory: async_sessionmaker[AsyncSession],
    message: AbstractIncomingMessage,
    *,
    sources: Mapping[str, BrokerSource],
    consumer_name: str,
) -> None:
    """Authenticate before DB access. ACK only after the audit row and inbox commit."""
    try:
        envelope = authenticated_envelope(message, sources=sources, audience="audit")
        issuer = sources[str(message.headers["key_id"])].key.issuer
        validate_source(envelope, issuer)
        envelope = envelope.model_copy(
            update={
                "payload": {**envelope.payload, "source_service": issuer},
            }
        )
        AuditEventPayload.model_validate(envelope.payload)
        async with factory() as db, db.begin():
            await handle_event(db, envelope, consumer_name=consumer_name)
    except (AuthenticationRequiredError, ValidationFailedError, ValidationError) as exc:
        # Only opaque IDs and routes already admitted by policy; never payload/header text.
        try:
            message_id = str(uuid.UUID(str(message.message_id)))
        except (ValueError, TypeError, AttributeError):
            message_id = None
        routes = {route for source in sources.values() for route in source.key.operations}
        logging.getLogger(__name__).warning(
            "%s",
            json.dumps(
                {
                    "event": "audit.rejected",
                    "error_type": type(exc).__name__,
                    "message_id": message_id,
                    "event_type": message.routing_key if message.routing_key in routes else None,
                },
                sort_keys=True,
            ),
        )
        await message.reject(requeue=False)
        return
    # Transient database failures escape unacknowledged to the reconnect supervisor.
    await message.ack()


async def run_consumer(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not settings.broker_url or not settings.source_credentials:
        raise ValueError("Audit consumer requires a broker and authenticated source credentials")
    sources = {key: value.source() for key, value in settings.source_credentials.items()}
    routes = tuple(
        sorted({route for source in sources.values() for route in source.key.operations})
    )
    logger = logging.getLogger(__name__)
    while True:
        try:
            async with confirmed_channel(settings.broker_url) as channel:
                queue = await declare_consumer_queue(
                    channel,
                    exchange_name=settings.consumer_exchange,
                    queue_name=settings.consumer_queue,
                    dead_letter_exchange=settings.consumer_dead_letter_exchange,
                    routes=routes,
                    prefetch=1,
                    single_active_consumer=True,
                )
                async with queue.iterator() as messages:
                    async for message in messages:
                        await receive_audit(
                            session_factory,
                            message,
                            sources=sources,
                            consumer_name=settings.consumer_name,
                        )
        except Exception as exc:
            logger.warning("Audit consumer reconnect: %s", type(exc).__name__)
            await asyncio.sleep(5)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # required environment
    engine = create_engine(settings.database_url)
    try:
        await run_consumer(settings, create_session_factory(engine))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
