"""The mandatory cross-tenant isolation test for ``audit_event`` (CLAUDE.md §7).

The highest-value test here: seed two tenants, read as one, assert the other's rows are
absent — the session-level tenant filter, not per-query discipline, is what enforces it.
"""

from __future__ import annotations

import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditEvent
from audit.tasks.consume import handle_event
from tests.seed import audit_envelope

pytestmark = pytest.mark.asyncio

_CONSUMER = "audit-consumer"


async def test_one_tenant_never_sees_anothers_events(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await handle_event(session, audit_envelope(tenant_id=tenant_a), consumer_name=_CONSUMER)
    await handle_event(session, audit_envelope(tenant_id=tenant_b), consumer_name=_CONSUMER)
    await handle_event(session, audit_envelope(tenant_id=tenant_b), consumer_name=_CONSUMER)
    await session.commit()

    with tenant_scope(tenant_a):
        rows = list((await session.scalars(select(AuditEvent))).all())
        assert len(rows) == 1
        assert all(r.tenant_id == tenant_a for r in rows)
        assert int(await session.scalar(select(func.count(AuditEvent.id))) or 0) == 1

    with tenant_scope(tenant_b):
        assert int(await session.scalar(select(func.count(AuditEvent.id))) or 0) == 2

    # The whole picture is only reachable through the audited escape hatch.
    with unfiltered():
        assert int(await session.scalar(select(func.count(AuditEvent.id))) or 0) == 3


async def test_a_query_with_no_tenant_in_context_is_refused(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await handle_event(session, audit_envelope(tenant_id=tenant_a), consumer_name=_CONSUMER)
    await session.commit()
    # Outside any tenant_scope/unfiltered block, a tenant-scoped read raises rather than
    # leaking across tenants (CLAUDE.md §5.3).
    with pytest.raises(TenantContextError):
        await session.scalars(select(AuditEvent))
