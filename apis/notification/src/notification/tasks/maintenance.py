"""Scheduled maintenance jobs (docs/notification-operations.md, docs/notification.md §6).

Four background passes, all pure DB logic (no broker, no provider), each returning how
much it touched so the scheduler can log it:

* :func:`purge_expired_content` — cryptographic purge of rendered content and raw callback
  payloads past retention. Nulls the ciphertext, keeps the hashes and normalized evidence.
* :func:`detect_stuck_deliveries` flags an old ``sending`` delivery for
  reconciliation. A blind retry could duplicate a provider-accepted send.
* :func:`reconcile_unmatched` — a provider event that arrived before its delivery had a
  ``provider_message_id`` is re-queued for the normalizer once the delivery exists.
* :func:`due_retry_deliveries` — the deliveries whose backoff has elapsed, for the
  dispatcher to re-attempt (the send itself is live transport, not part of this pass).

These are cross-tenant platform jobs: the scan runs under a single audited
``unfiltered()`` and per-row work that needs isolation re-enters the row's tenant scope.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import (
    Attachment,
    NotificationContent,
    NotificationDelivery,
    NotificationJob,
    NotificationRequest,
    ProviderEvent,
)
from notification.ownership import space_scope


async def purge_expired_content(
    db: AsyncSession,
    *,
    now: dt.datetime | None = None,
    provider_event_retention_days: int = 90,
    content_retention_days: int = 90,
    limit: int = 500,
) -> int:
    """Null expired content and raw callback payloads; keep hashes. Returns rows purged."""
    now = now or utcnow()
    purged = 0
    with unfiltered():
        contents = list(
            (
                await db.scalars(
                    select(NotificationContent)
                    .where(
                        NotificationContent.expires_at <= now,
                        NotificationContent.purged_at.is_(None),
                    )
                    .limit(limit)
                )
            ).all()
        )
        for content in contents:
            content.subject_ciphertext = None
            content.body_text_ciphertext = None
            content.body_html_ciphertext = None
            content.payload_ciphertext = None
            content.purged_at = now
            purged += 1

        cutoff = now - dt.timedelta(days=provider_event_retention_days)
        events = list(
            (
                await db.scalars(
                    select(ProviderEvent)
                    .where(
                        ProviderEvent.received_at <= cutoff,
                        ProviderEvent.payload_ciphertext.is_not(None),
                    )
                    .limit(limit)
                )
            ).all()
        )
        for event in events:
            event.payload_ciphertext = None  # keep payload_sha256 as evidence
            purged += 1
    with unfiltered():
        requests = await db.scalars(
            select(NotificationRequest)
            .where(
                NotificationRequest.received_at <= now - dt.timedelta(days=content_retention_days),
                NotificationRequest.context_ciphertext.is_not(None),
            )
            .limit(limit)
        )
        for request in requests:
            request.context_ciphertext = None
            purged += 1
        attachments = await db.scalars(
            select(Attachment)
            .where(Attachment.expires_at <= now, Attachment.purged_at.is_(None))
            .limit(limit)
        )
        for attachment in attachments:
            attachment.filename_ciphertext = b""
            attachment.storage_key = "purged:" + str(attachment.id)
            attachment.purged_at = now
            purged += 1
        stuck = await db.scalars(
            select(NotificationJob)
            .where(
                NotificationJob.status == "running",
                NotificationJob.started_at < now - dt.timedelta(minutes=15),
            )
            .limit(limit)
        )
        for job in stuck:
            job.status, job.reason_code, job.completed_at = (
                "failed",
                "interrupted_provider_check",
                now,
            )
        await db.flush()
    return purged


async def detect_stuck_deliveries(
    db: AsyncSession,
    *,
    now: dt.datetime | None = None,
    stuck_after_seconds: int = 900,
    limit: int = 500,
) -> int:
    """Flag ambiguous sends for reconciliation; never retry them blindly."""
    now = now or utcnow()
    cutoff = now - dt.timedelta(seconds=stuck_after_seconds)
    reset = 0
    with unfiltered():
        rows = list(
            (
                await db.scalars(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.status == "sending",
                        NotificationDelivery.updated_at < cutoff,
                    )
                    .limit(limit)
                )
            ).all()
        )
        for delivery in rows:
            if delivery.status_reason == "ambiguous_stuck_send":
                continue
            delivery.status_reason = "ambiguous_stuck_send"
            reset += 1
    with unfiltered():  # bounded cross-owner maintenance writes, never a request path
        await db.flush()
    return reset


async def reconcile_unmatched(db: AsyncSession, *, limit: int = 500) -> int:
    """Re-queue unmatched provider events whose delivery now exists. Returns rows requeued."""
    requeued = 0
    with unfiltered():
        events = list(
            (
                await db.scalars(
                    select(ProviderEvent)
                    .where(
                        ProviderEvent.processing_status == "unmatched",
                        ProviderEvent.provider_message_id.is_not(None),
                    )
                    .limit(limit)
                )
            ).all()
        )
    for event in events:
        with tenant_scope(event.tenant_id), space_scope(event.space_id):
            match = await db.scalar(
                select(NotificationDelivery.id).where(
                    NotificationDelivery.provider_account_id == event.provider_account_id,
                    NotificationDelivery.provider_message_id == event.provider_message_id,
                )
            )
            if match is not None:
                event.processing_status = "pending"
                event.processed_at = None
                requeued += 1
    with unfiltered():  # bounded cross-owner maintenance writes, never a request path
        await db.flush()
    return requeued


async def due_retry_deliveries(
    db: AsyncSession, *, now: dt.datetime | None = None, limit: int = 200
) -> list[uuid.UUID]:
    """Delivery ids whose backoff has elapsed, for the dispatcher to re-attempt."""
    now = now or utcnow()
    with unfiltered():
        rows = await db.scalars(
            select(NotificationDelivery.id)
            .where(
                NotificationDelivery.status == "retry_wait",
                NotificationDelivery.next_attempt_at <= now,
            )
            .order_by(NotificationDelivery.next_attempt_at)
            .limit(limit)
        )
        return list(rows.all())


async def expire_purged_deliveries(
    db: AsyncSession, *, now: dt.datetime | None = None, limit: int = 500
) -> int:
    """Transition deliveries with expired/purged content to terminal state.

    Returns rows expired.
    """
    now = now or utcnow()
    expired = 0
    with unfiltered():
        rows = list(
            (
                await db.scalars(
                    select(NotificationDelivery)
                    .join(
                        NotificationContent,
                        NotificationDelivery.id == NotificationContent.delivery_id,
                    )
                    .where(
                        NotificationDelivery.status.in_({"pending", "scheduled", "retry_wait"}),
                        NotificationContent.expires_at <= now,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for delivery in rows:
            delivery.status = "expired"
            delivery.status_reason = "content_expired"
            delivery.completed_at = now
            delivery.updated_at = now
            expired += 1
    with unfiltered():  # bounded cross-owner maintenance writes, never a request path
        await db.flush()
    return expired
