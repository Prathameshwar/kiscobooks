"""Scheduled maintenance orchestration (docs/notification-operations.md).

``run_maintenance_once`` runs one pass of every periodic job in a single transaction and
returns a summary — this is the tested unit. ``run_scheduler`` is the thin loop that calls
it on an interval in prod/CI (no-cover transport). Dispatch of due retries is left to the
dispatcher process; this pass only surfaces the due delivery ids.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from billing_platform.db import create_engine, unfiltered
from sqlalchemy.ext.asyncio import AsyncSession

from notification.config import Settings
from notification.ownership import session_factory as notification_session_factory
from notification.security import AesGcmCipher
from notification.tasks.configuration import run_configuration_jobs
from notification.tasks.maintenance import (
    detect_stuck_deliveries,
    due_retry_deliveries,
    expire_purged_deliveries,
    purge_expired_content,
    reconcile_unmatched,
)
from notification.tasks.normalize import normalize_pending

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MaintenanceSummary:
    normalized: int = 0
    purged: int = 0
    stuck_flagged: int = 0
    expired: int = 0
    requeued: int = 0
    due_retries: int = 0


async def run_maintenance_once(
    db: AsyncSession,
    *,
    stuck_sending_seconds: int = 900,
    cipher: AesGcmCipher | None = None,
    content_retention_days: int = 90,
    provider_event_retention_days: int = 90,
) -> MaintenanceSummary:
    """One pass of every periodic job. The caller owns the transaction."""
    summary = MaintenanceSummary()
    summary.normalized = await normalize_pending(db, cipher=cipher)
    summary.requeued = await reconcile_unmatched(db)
    summary.stuck_flagged = await detect_stuck_deliveries(
        db, stuck_after_seconds=stuck_sending_seconds
    )
    summary.purged = await purge_expired_content(
        db,
        content_retention_days=content_retention_days,
        provider_event_retention_days=provider_event_retention_days,
    )
    summary.expired = await expire_purged_deliveries(db)
    summary.due_retries = len(await due_retry_deliveries(db))
    return summary


async def run_scheduler(  # pragma: no cover - interval loop, exercised in CI
    settings: Any,
    session_factory: Any,
    *,
    interval_seconds: int = 60,
    cipher: AesGcmCipher | None = None,
) -> None:
    """Run maintenance forever on an interval. Each pass is its own transaction."""
    while True:
        try:
            async with session_factory() as db:
                try:
                    with unfiltered():  # bounded, audited cross-owner maintenance only
                        await run_maintenance_once(
                            db,
                            stuck_sending_seconds=settings.stuck_sending_seconds,
                            cipher=cipher,
                            content_retention_days=getattr(settings, "content_retention_days", 90),
                            provider_event_retention_days=getattr(
                                settings, "provider_event_retention_days", 90
                            ),
                        )
                        await db.commit()
                    await run_configuration_jobs(session_factory, settings)
                except Exception:
                    await db.rollback()
                    raise
        except Exception:
            # Do not log database exceptions or payloads; they can contain private data.
            logger.error("notification maintenance pass failed; retrying next interval")
        await asyncio.sleep(interval_seconds)


async def main(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    factory = notification_session_factory(engine)
    try:
        await run_scheduler(
            settings,
            factory,
            cipher=AesGcmCipher(_cipher_key(settings)),
        )
    finally:
        await engine.dispose()


def _cipher_key(settings: Settings) -> bytes:
    key = settings.data_encryption_key.get_secret_value().encode()
    return key if len(key) == 32 else hashlib.sha256(key).digest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(main(Settings(_env_file=args.env_file)))  # type: ignore[call-arg]
