"""Engine construction and the commit/rollback scope."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool

from billing_platform.db.session import create_engine, session_scope
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from tests.models import TenantThing


def test_mariadb_engine_is_read_committed_with_a_sized_pool() -> None:
    """Rule 4.2: READ COMMITTED makes ``SELECT ... FOR UPDATE`` number allocation
    safe without gap locks. Asserted on the engine because the default is
    REPEATABLE READ and nothing else would notice."""
    engine = create_engine("mysql+asyncmy://u:p@localhost:3306/identity", pool_size=5)

    assert engine.dialect.name == "mysql"
    assert engine.sync_engine.dialect._on_connect_isolation_level == "READ COMMITTED"
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 5


def test_sqlite_engine_omits_isolation_level_and_pool_sizing() -> None:
    """SQLite has neither, and passing them raises at construction — which is why
    the test suite's own engine exercises this branch."""
    engine = create_engine("sqlite+aiosqlite:///:memory:")

    assert engine.dialect.name == "sqlite"
    assert engine.sync_engine.dialect._on_connect_isolation_level is None


async def _count(session: AsyncSession) -> int:
    with unfiltered():
        result = await session.execute(select(func.count()).select_from(TenantThing))
    return int(result.scalar_one())


async def test_session_scope_commits_on_success(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    async with session_scope(factory) as session:
        session.add(TenantThing(tenant_id=tenant_a, name="kept"))

    async with factory() as check:
        with tenant_scope(tenant_a):
            rows = (await check.execute(select(TenantThing))).scalars().all()
    assert [r.name for r in rows] == ["kept"]


async def test_session_scope_rolls_back_and_reraises(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A failed request must leave no row *and* no audit event (invariant 8),
    and the error must reach the handler rather than be swallowed."""
    with pytest.raises(RuntimeError, match="boom"):
        async with session_scope(factory) as session:
            session.add(TenantThing(tenant_id=tenant_a, name="dropped"))
            await session.flush()
            raise RuntimeError("boom")

    async with factory() as check:
        assert await _count(check) == 0
