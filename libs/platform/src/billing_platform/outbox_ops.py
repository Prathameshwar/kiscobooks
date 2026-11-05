"""Bounded operator inventory and explicit-ID recovery; never rewrite event evidence."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow


async def inventory(
    factory: async_sessionmaker[AsyncSession],
    event_types: frozenset[str],
    *,
    maximum_attempts: int = 12,
    occurred_after: dt.datetime | None = None,
    sample_limit: int = 100,
) -> dict[str, Any]:
    if not 0 <= sample_limit <= 100:
        raise ValueError("inventory sample limit must be between 0 and 100")
    async with factory() as db:
        scope = Outbox.event_type.in_(event_types)
        pending = (
            scope,
            Outbox.published_at.is_(None),
            *((Outbox.occurred_at >= occurred_after,) if occurred_after else ()),
        )
        count = await db.scalar(select(func.count()).select_from(Outbox).where(*pending))
        oldest = await db.scalar(select(func.min(Outbox.occurred_at)).where(*pending))
        exhausted = await db.scalar(
            select(func.count())
            .select_from(Outbox)
            .where(*pending, Outbox.attempt_count >= maximum_attempts)
        )
        rows = list(
            await db.scalars(
                select(Outbox)
                .where(*pending)
                .order_by(Outbox.available_at, Outbox.id)
                .limit(sample_limit)
            )
        )
        return {
            "pending": count,
            "exhausted": exhausted,
            "oldest_occurred_at": oldest.isoformat() if oldest else None,
            "oldest_age_seconds": max(0, int((utcnow() - oldest).total_seconds())) if oldest else 0,
            "sample": [
                {
                    "message_id": str(row.message_id),
                    "event_type": row.event_type,
                    "attempts": row.attempt_count,
                    "available_at": row.available_at.isoformat(),
                    "last_error": row.last_error,
                }
                for row in rows
            ],
        }


async def retry_selected(
    factory: async_sessionmaker[AsyncSession],
    event_types: frozenset[str],
    message_ids: list[uuid.UUID],
    *,
    apply: bool = False,
) -> list[dict[str, Any]]:
    if not message_ids or len(message_ids) > 100 or len(set(message_ids)) != len(message_ids):
        raise ValueError("select between 1 and 100 distinct message IDs")
    async with factory() as db, db.begin():
        rows = list(
            await db.scalars(
                select(Outbox)
                .where(Outbox.message_id.in_(message_ids), Outbox.event_type.in_(event_types))
                .with_for_update()
            )
        )
        if len(rows) != len(message_ids) or any(row.published_at is not None for row in rows):
            raise ValueError("every selected message must be a pending event of this publisher")
        report = [
            {
                "message_id": str(row.message_id),
                "event_type": row.event_type,
                "attempts": row.attempt_count,
                "apply": apply,
            }
            for row in rows
        ]
        if apply:
            for row in rows:
                row.attempt_count = 0
                row.available_at = utcnow() - dt.timedelta(seconds=1)
                row.last_error = None
        return report
