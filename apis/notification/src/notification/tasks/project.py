"""Projection consumers for identity-mastered data (docs/notification.md, §4.3).

``identity`` owns ``user_notification_preference``; this service holds a read-only
projection (``notification_preference``) it reads at send time. The projection applies an
event only when its ``source_version`` is newer than the stored one, so redelivery and
out-of-order events are idempotent — last-writer-by-version wins.

``project_preference`` is pure DB logic, tested on SQLite. ``run_preference_projector`` is
the thin aio-pika loop that binds it to the broker (prod/CI transport, no-cover).
"""

from __future__ import annotations

from typing import Any

from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.events import PreferenceChanged
from notification.models import NotificationPreference

APPLIED = "applied"
STALE = "stale"


async def project_preference(db: AsyncSession, envelope: MessageEnvelope) -> str:
    """Upsert the preference projection from a master event. Returns ``applied`` or
    ``stale`` (an older/equal source version is ignored). Caller owns the transaction."""
    payload = PreferenceChanged.model_validate(envelope.payload)
    now = utcnow()
    with tenant_scope(envelope.tenant_id):
        existing = await db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.subject_type == payload.subject_type,
                NotificationPreference.subject_id == payload.subject_id,
                NotificationPreference.event_key == payload.event_key,
                NotificationPreference.channel == payload.channel,
            )
        )
        if existing is None:
            db.add(
                NotificationPreference(
                    id=uuid7(),
                    tenant_id=envelope.tenant_id,
                    subject_type=payload.subject_type,
                    subject_id=payload.subject_id,
                    event_key=payload.event_key,
                    channel=payload.channel,
                    is_enabled=payload.is_enabled,
                    source_version=payload.source_version,
                    source_updated_at=payload.source_updated_at,
                    projected_at=now,
                )
            )
            outcome = APPLIED
        elif payload.source_version > existing.source_version:
            existing.is_enabled = payload.is_enabled
            existing.source_version = payload.source_version
            existing.source_updated_at = payload.source_updated_at
            existing.projected_at = now
            outcome = APPLIED
        else:
            outcome = STALE  # older or duplicate version — ignore
        await db.flush()
        return outcome


async def run_preference_projector(  # pragma: no cover - live-broker transport
    settings: Any, session_factory: Any
) -> None:
    """Legacy entrypoint is intentionally disabled: it did not authenticate broker sources."""
    raise RuntimeError("use the authenticated, source-scoped notification.tasks.identity consumer")
