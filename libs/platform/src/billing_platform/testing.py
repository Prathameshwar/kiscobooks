"""Test fixtures shared by every service's suite.

Two engines, deliberately:

* **SQLite/aiosqlite** for logic that is dialect-independent — the tenant filter,
  types, mixins, domain rules. Fast, no Docker.
* **MariaDB via testcontainers** for anything where the dialect *is* the subject:
  collation, ``DECIMAL`` truncation, NULL-in-UNIQUE, generated columns, DDL.
  Those tests carry the ``mariadb`` marker and are skipped without Docker.

Never assert a MariaDB behaviour against SQLite. The two disagree on exactly the
things that cause the bugs this platform cares about, which is why integration
paths are never mocked at the driver level (CLAUDE.md §7).

The fixtures live here rather than in each service's ``conftest.py`` so seven
suites cannot drift on how a session is built — the same reason the tenant filter
lives in this library. A service conftest re-exports them:

    from billing_platform.testing import (  # noqa: F401
        engine, factory, session, tenant_a, tenant_b,
    )
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from billing_platform.db.base import Base
from billing_platform.db.session import create_engine, create_session_factory
from billing_platform.ids import uuid7

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


def table_of(model: type[Base]) -> Table:
    """The mapped ``Table`` for a model.

    ``model.__table__`` is typed ``FromClause``, which has no ``name``, ``indexes``
    or ``constraints`` under mypy strict. Narrowing here once keeps every
    schema-convention assertion readable, in all seven suites — each one asserts its
    own index and constraint names, so this would otherwise be copied seven times.
    """
    table = model.__table__
    assert isinstance(table, Table)
    return table


async def make_sqlite_engine() -> AsyncEngine:
    """In-memory engine with the full schema created.

    Every engine gets its own database, so tests never share state. Only tables
    already registered on ``Base.metadata`` are created — a service conftest must
    import its models before this runs.

    **Foreign keys are enforced.** SQLite ignores them unless asked, and a suite
    that silently ignores foreign keys reports green on exactly the bugs the keys
    exist to prevent — a dangling `country_code`, a seed run in the wrong order, a
    composite `(country_code, state_code)` pair that does not exist. InnoDB enforces
    them, so the fixture must too, or the two engines disagree about what the schema
    means.
    """
    eng = create_engine(SQLITE_URL)

    @event.listens_for(eng.sync_engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        # `Any` because the DBAPI connection is aiosqlite's sync-facing adapter and
        # carries no stubs. Via a cursor rather than `.execute` for the same reason:
        # it is the shape every DBAPI guarantees.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return eng


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = await make_sqlite_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest_asyncio.fixture
async def session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as s:
        yield s


@pytest.fixture
def tenant_a() -> uuid.UUID:
    return uuid7()


@pytest.fixture
def tenant_b() -> uuid.UUID:
    """A second tenant, so the isolation assertion is always available.

    Every table with ``tenant_id`` needs a two-tenant test (CLAUDE.md §7), so
    the second tenant is a fixture rather than something each test invents.
    """
    return uuid7()
