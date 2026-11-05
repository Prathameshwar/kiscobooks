"""Inspect delivery without payloads; explicitly release one exhausted current event."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from billing_platform.db import create_engine, create_session_factory
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.events.audit_contract import AUDIT_EVENT_TYPES
from identity.tasks.audit_publisher import PublisherSettings


async def delivery_status(db: AsyncSession, settings: PublisherSettings) -> dict[str, object]:
    pending = (Outbox.event_type.in_(AUDIT_EVENT_TYPES), Outbox.published_at.is_(None))
    eligible = (*pending, Outbox.occurred_at >= settings.publish_after)
    count = int(await db.scalar(select(func.count()).select_from(Outbox).where(*pending)) or 0)
    held = int(
        await db.scalar(
            select(func.count())
            .select_from(Outbox)
            .where(
                *pending,
                Outbox.occurred_at < settings.publish_after,
            )
        )
        or 0
    )
    exhausted = int(
        await db.scalar(
            select(func.count())
            .select_from(Outbox)
            .where(
                *eligible,
                Outbox.attempt_count >= settings.maximum_attempts,
            )
        )
        or 0
    )
    oldest = await db.scalar(select(func.min(Outbox.occurred_at)).where(*eligible))
    rows = (
        await db.execute(
            select(
                Outbox.message_id,
                Outbox.event_type,
                Outbox.attempt_count,
                Outbox.last_error,
            )
            .where(*eligible, Outbox.attempt_count >= settings.maximum_attempts)
            .order_by(Outbox.occurred_at, Outbox.id)
            .limit(50)
        )
    ).all()
    return {
        "pending": count,
        "historical_held": held,
        "exhausted": exhausted,
        "oldest_pending_at": oldest.isoformat() if oldest else None,
        "exhausted_sample": [
            {
                "message_id": str(r.message_id),
                "event_type": r.event_type,
                "attempt_count": r.attempt_count,
                "error_class": r.last_error,
            }
            for r in rows
        ],
    }


async def retry_event(db: AsyncSession, settings: PublisherSettings, message_id: uuid.UUID) -> None:
    row = await db.scalar(
        select(Outbox)
        .where(
            Outbox.message_id == message_id,
            Outbox.event_type.in_(AUDIT_EVENT_TYPES),
        )
        .with_for_update()
    )
    if row is None:
        raise NotFoundError("audit event not found")
    if row.published_at is not None or row.occurred_at < settings.publish_after:
        raise ConflictError("published or historically held events cannot be retried here")
    if row.attempt_count < settings.maximum_attempts:
        raise ConflictError("event is already eligible for automatic retry")
    row.attempt_count = 0
    row.last_error = None
    row.available_at = utcnow()


async def main(message_id: uuid.UUID | None) -> None:
    settings = PublisherSettings()  # type: ignore[call-arg]  # required environment
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as db, db.begin():
            if message_id is not None:
                await retry_event(db, settings, message_id)
                await db.flush()
            print(json.dumps(await delivery_status(db, settings)))  # noqa: T201  operator command
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry", type=uuid.UUID, help="one reviewed exhausted message ID")
    asyncio.run(main(parser.parse_args().retry))
