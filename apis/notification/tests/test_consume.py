"""Integration tests for the send-command consumer (docs/notification.md §5).

Drives ``handle_send_command`` against a seeded email route and asserts the gate
outcomes and that a delivery + encrypted content are created for a passing channel,
idempotently. SQLite via the shared session fixture — no broker.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import (
    NotificationContent,
    NotificationDelivery,
    NotificationPreference,
    NotificationRequest,
    Suppression,
)
from notification.tasks.consume import handle_send_command
from tests.notif_seed import CIPHER, HMAC, KEY_REF, NOW, envelope, seed_email_route

pytestmark = pytest.mark.asyncio


async def _count(session: AsyncSession, model: Any, tenant: uuid.UUID) -> int:
    with tenant_scope(tenant):
        return int(await session.scalar(select(func.count(model.id))) or 0)


async def test_happy_path_creates_delivery_and_content(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    result = await handle_send_command(
        session, envelope(tenant_a, company, subject), cipher=CIPHER, key_ref=KEY_REF
    )
    await session.commit()
    assert result.deliveries_created == 1
    assert result.outcomes == {"email": "send"}
    assert await _count(session, NotificationDelivery, tenant_a) == 1
    with tenant_scope(tenant_a):
        content = (await session.scalars(select(NotificationContent))).all()
    assert len(content) == 1
    row = content[0]
    assert row.body_text_ciphertext is not None
    cipher_bytes = row.body_text_ciphertext
    # The ciphertext decrypts back to the rendered body, bound to the delivery id.
    assert CIPHER.decrypt(cipher_bytes, associated_data=row.delivery_id.bytes) == b"Hello Ada"


async def test_replay_is_idempotent(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    env = envelope(tenant_a, company, subject)
    first = await handle_send_command(session, env, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()
    second = await handle_send_command(session, env, cipher=CIPHER, key_ref=KEY_REF)
    await session.commit()
    assert second.deduplicated is True
    assert second.request_id == first.request_id
    assert await _count(session, NotificationRequest, tenant_a) == 1
    assert await _count(session, NotificationDelivery, tenant_a) == 1


async def test_preference_off_skips(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    with unfiltered():
        session.add(
            NotificationPreference(
                id=uuid7(),
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=subject,
                event_key="invoice.posted",
                channel="email",
                is_enabled=False,
                source_version=1,
                source_updated_at=NOW,
                projected_at=NOW,
            )
        )
        await session.commit()
    result = await handle_send_command(
        session, envelope(tenant_a, company, subject), cipher=CIPHER, key_ref=KEY_REF
    )
    await session.commit()
    assert result.outcomes == {"email": "skipped"}
    assert await _count(session, NotificationDelivery, tenant_a) == 0


async def _add_global_suppression(
    session: AsyncSession, tenant: uuid.UUID, source_event_key: str
) -> None:
    with unfiltered():
        session.add(
            Suppression(
                id=uuid7(),
                tenant_id=tenant,
                channel="email",
                destination_hmac=HMAC,
                scope_type="global",
                scope_key="",
                reason="hard_bounce",
                source="ses",
                source_event_key=source_event_key,
                valid_from=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            )
        )
        await session.commit()


async def test_active_suppression_suppresses(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    await _add_global_suppression(session, tenant_a, "b1")
    result = await handle_send_command(
        session, envelope(tenant_a, company, subject), cipher=CIPHER, key_ref=KEY_REF
    )
    await session.commit()
    assert result.outcomes == {"email": "suppressed"}
    assert await _count(session, NotificationDelivery, tenant_a) == 0


async def test_security_bypasses_suppression(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="password.changed",
        category="security",
    )
    await _add_global_suppression(session, tenant_a, "b2")
    result = await handle_send_command(
        session,
        envelope(tenant_a, company, subject, category="security", event_key="password.changed"),
        cipher=CIPHER,
        key_ref=KEY_REF,
    )
    await session.commit()
    assert result.outcomes == {"email": "send"}
    assert await _count(session, NotificationDelivery, tenant_a) == 1
