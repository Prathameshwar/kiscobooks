"""Preference projection consumer — version-ordered, idempotent (docs/notification.md §4.3)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import NotificationPreference
from notification.tasks.project import APPLIED, STALE, project_preference

pytestmark = pytest.mark.asyncio

_NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


def _envelope(
    tenant: uuid.UUID, subject: uuid.UUID, *, enabled: bool, version: int
) -> MessageEnvelope:
    payload: dict[str, Any] = {
        "subject_type": "user",
        "subject_id": str(subject),
        "event_key": "invoice.posted",
        "channel": "email",
        "is_enabled": enabled,
        "source_version": version,
        "source_updated_at": _NOW.isoformat(),
    }
    return MessageEnvelope(
        message_id=uuid7(),
        tenant_id=tenant,
        event_type="user_notification_preference.changed",
        schema_version=1,
        occurred_at=_NOW,
        payload=payload,
    )


async def _stored(session: AsyncSession, tenant: uuid.UUID) -> NotificationPreference | None:
    with tenant_scope(tenant):
        return (await session.scalars(select(NotificationPreference))).one_or_none()


async def _apply(
    session: AsyncSession, tenant: uuid.UUID, subject: uuid.UUID, *, enabled: bool, version: int
) -> str:
    outcome = await project_preference(
        session, _envelope(tenant, subject, enabled=enabled, version=version)
    )
    await session.commit()
    return outcome


async def test_projection_applies_and_is_version_ordered(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    subject = uuid7()
    assert await _apply(session, tenant_a, subject, enabled=False, version=2) == APPLIED
    row = await _stored(session, tenant_a)
    assert row is not None and row.is_enabled is False and row.source_version == 2

    # An older version is ignored (out-of-order / replay).
    assert await _apply(session, tenant_a, subject, enabled=True, version=1) == STALE
    row = await _stored(session, tenant_a)
    assert row is not None and row.is_enabled is False and row.source_version == 2

    # A newer version supersedes.
    assert await _apply(session, tenant_a, subject, enabled=True, version=3) == APPLIED
    row = await _stored(session, tenant_a)
    assert row is not None and row.is_enabled is True and row.source_version == 3


async def test_projection_replay_of_same_version_is_stale(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    subject = uuid7()
    env = _envelope(tenant_a, subject, enabled=True, version=5)
    assert await project_preference(session, env) == APPLIED
    await session.commit()
    assert await project_preference(session, env) == STALE  # equal version → no effect
    await session.commit()
