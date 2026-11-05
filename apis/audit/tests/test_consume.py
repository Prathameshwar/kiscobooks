"""The ingestion consumer against a real session (docs/audit.md §2.2, §4.2)."""

from __future__ import annotations

import uuid

import pytest
from billing_platform.db.tenant_context import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditEvent
from audit.tasks.consume import handle_event
from tests.seed import audit_envelope

pytestmark = pytest.mark.asyncio

_CONSUMER = "audit-consumer"


async def _count(session: AsyncSession, tenant: uuid.UUID) -> int:
    with tenant_scope(tenant):
        return int(await session.scalar(select(func.count(AuditEvent.id))) or 0)


async def _events(session: AsyncSession, tenant: uuid.UUID) -> list[AuditEvent]:
    with tenant_scope(tenant):
        return list(
            (await session.scalars(select(AuditEvent).order_by(AuditEvent.sequence.asc()))).all()
        )


async def test_first_event_starts_the_chain(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    result = await handle_event(
        session, audit_envelope(tenant_id=tenant_a), consumer_name=_CONSUMER
    )
    await session.commit()
    assert result.sequence == 1
    events = await _events(session, tenant_a)
    assert len(events) == 1
    assert events[0].prev_hash is None
    assert len(events[0].row_hash) == 32


async def test_second_event_links_to_the_first(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await handle_event(session, audit_envelope(tenant_id=tenant_a), consumer_name=_CONSUMER)
    await session.commit()
    await handle_event(
        session, audit_envelope(tenant_id=tenant_a, action="updated"), consumer_name=_CONSUMER
    )
    await session.commit()

    events = await _events(session, tenant_a)
    assert [e.sequence for e in events] == [1, 2]
    # The second row's prev_hash is the first row's row_hash — the chain link (§4.2).
    assert events[1].prev_hash == events[0].row_hash


async def test_redelivery_is_one_effect(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    envelope = audit_envelope(tenant_id=tenant_a)
    first = await handle_event(session, envelope, consumer_name=_CONSUMER)
    await session.commit()
    second = await handle_event(session, envelope, consumer_name=_CONSUMER)
    await session.commit()

    assert first.deduplicated is False
    assert second.deduplicated is True
    assert await _count(session, tenant_a) == 1  # one row, not two


async def test_chains_are_independent_per_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await handle_event(session, audit_envelope(tenant_id=tenant_a), consumer_name=_CONSUMER)
    await handle_event(session, audit_envelope(tenant_id=tenant_b), consumer_name=_CONSUMER)
    await session.commit()

    a_events = await _events(session, tenant_a)
    b_events = await _events(session, tenant_b)
    # Each tenant's chain starts at 1 with no prev_hash — a shared counter would give one 2.
    assert a_events[0].sequence == 1 and a_events[0].prev_hash is None
    assert b_events[0].sequence == 1 and b_events[0].prev_hash is None
