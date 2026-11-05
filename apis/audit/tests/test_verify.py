"""The scheduled chain-verification job against a real session (docs/audit.md §4.2)."""

from __future__ import annotations

import uuid

import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditEvent
from audit.tasks.consume import handle_event
from audit.tasks.verify import verify_all_chains, verify_tenant_chain
from tests.seed import audit_envelope

pytestmark = pytest.mark.asyncio

_CONSUMER = "audit-consumer"


async def _seed(session: AsyncSession, tenant: uuid.UUID, count: int) -> None:
    for _ in range(count):
        await handle_event(session, audit_envelope(tenant_id=tenant), consumer_name=_CONSUMER)
    await session.commit()


async def test_intact_chain_verifies_clean(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await _seed(session, tenant_a, 5)
    assert await verify_tenant_chain(session, tenant_a) == []
    assert await verify_all_chains(session) == {}


async def test_event_with_fractional_changes_ingests_and_verifies(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # A float in `changes` must ingest (not dead-letter) and the stored row_hash must still
    # verify after the write→DB→read round-trip (regression for the _canonical float gap).
    await handle_event(
        session,
        audit_envelope(
            tenant_id=tenant_a,
            category="money",
            action="posted",
            changes={"tax_rate": {"from": 18.0, "to": 12.5}, "amount": 1234.5},
        ),
        consumer_name=_CONSUMER,
    )
    await session.commit()
    assert await verify_tenant_chain(session, tenant_a) == []


async def test_a_tampered_row_is_reported(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await _seed(session, tenant_a, 5)

    # Simulate an out-of-band edit the INSERT/SELECT grant would forbid in production: flip
    # a stored content field without recomputing the hash. Verification must catch it.
    with unfiltered():
        target = await session.scalar(select(AuditEvent).where(AuditEvent.sequence == 3))
        assert target is not None
        target.action = "tampered"
        await session.commit()

    breaks = await verify_tenant_chain(session, tenant_a)
    assert any(b.sequence == 3 for b in breaks)
    broken = await verify_all_chains(session)
    assert tenant_a in broken


async def test_verification_is_scoped_per_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _seed(session, tenant_a, 3)
    await _seed(session, tenant_b, 3)
    # Reading one tenant's chain must never pull the other's rows into the recomputation.
    with tenant_scope(tenant_a):
        pass
    assert await verify_tenant_chain(session, tenant_a) == []
    assert await verify_tenant_chain(session, tenant_b) == []


async def test_paged_verification_checks_links_across_page_boundaries(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, 5)
    assert await verify_tenant_chain(session, tenant_a, page_size=2) == []
    with tenant_scope(tenant_a):
        target = await session.scalar(select(AuditEvent).where(AuditEvent.sequence == 3))
        assert target is not None
        target.prev_hash = b"x" * 32
        await session.commit()
    breaks = await verify_tenant_chain(session, tenant_a, page_size=2)
    assert any(b.sequence == 3 and "prior" in b.reason for b in breaks)


@pytest.mark.parametrize("page_size", [1, 2])
async def test_duplicate_sequence_at_page_boundary_cannot_verify_clean(
    session: AsyncSession, tenant_a: uuid.UUID, page_size: int
) -> None:
    await _seed(session, tenant_a, 1)
    with tenant_scope(tenant_a):
        original = await session.scalar(select(AuditEvent))
        assert original is not None
        # Same sequence/content/hash but a different physical PK. The verifier must inspect
        # both rows even though sequence is the field whose integrity it is checking.
        copy = {
            column.key: getattr(original, column.key) for column in AuditEvent.__table__.columns
        }
        copy["id"] = uuid.uuid4()
        session.add(AuditEvent(**copy))
        await session.commit()
    breaks = await verify_tenant_chain(session, tenant_a, page_size=page_size)
    assert any("sequence" in item.reason for item in breaks)
