"""Suite wiring for `audit`.

The session fixtures come from ``billing_platform.testing`` so seven service suites share
one definition of how a session is built. What is added here is the MySQL container,
because dialect behaviour — RANGE partitioning, collation, the ``BINARY(32)`` hashes — is
the whole reason the migration tests exist and none of it reproduces on SQLite.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from billing_platform.testing import (  # noqa: F401
    engine,
    factory,
    session,
    tenant_a,
    tenant_b,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Registers every model on Base.metadata before `create_all` in the shared fixtures.
from audit import models  # noqa: F401
from tests.alembic_support import docker_available, native_mysql_server
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET

#: MySQL 9.6 — the production version (tech-stack.md decision log, 2026-09-11).
MYSQL_IMAGE = "mysql:9.6"

_DB_NAME = "audit"
_DB_USER = "audit"
# Not a secret: a throwaway credential for an ephemeral container bound to a random
# localhost port and destroyed with the session (CLAUDE.md §5.9).
_DB_PASSWORD = "test-only-not-a-secret"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip container tests when no runtime is reachable, rather than erroring."""
    if native := os.environ.get("AUDIT_TEST_MYSQL_SERVER_URL"):
        native_mysql_server(native)  # Reject an app schema before any destructive fixture setup.
        return
    if docker_available():
        return
    skip = pytest.mark.skip(reason="no reachable container runtime; MySQL tests need Docker")
    for item in items:
        if "mysql" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def app(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> object:  # noqa: F811
    """The FastAPI app wired to the test's own SQLite engine (shared in-memory, StaticPool)."""
    from audit.config import Settings
    from audit.main import create_app

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=ACTOR_SECRET,  # type: ignore[arg-type]
        cursor_signing_secret=CURSOR_SECRET,  # type: ignore[arg-type]
    )
    application = create_app(settings)
    application.state.engine = engine
    application.state.session_factory = factory
    return application


@pytest_asyncio.fixture
async def client(app: object) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://audit.test") as c:
        yield c


@pytest.fixture(scope="session")
def mysql_url() -> Iterator[str]:
    """An async URL for a throwaway MySQL 9.6, one container per test session."""
    if native := os.environ.get("AUDIT_TEST_MYSQL_SERVER_URL"):
        server = native_mysql_server(native)
        database = "audit_test_" + uuid.uuid4().hex

        async def ddl(create: bool) -> None:
            if not re.fullmatch(r"audit_test_[0-9a-f]{32}", database):
                raise ValueError("refusing an unvalidated native test schema")
            engine = create_async_engine(server)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(f"{'CREATE' if create else 'DROP'} DATABASE `{database}`")
                    )
            finally:
                await engine.dispose()

        asyncio.run(ddl(True))
        try:
            yield server.set(database=database).render_as_string(hide_password=False)
        finally:
            asyncio.run(ddl(False))
        return
    from testcontainers.mysql import MySqlContainer

    container = MySqlContainer(
        image=MYSQL_IMAGE,
        username=_DB_USER,
        password=_DB_PASSWORD,
        dbname=_DB_NAME,
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"mysql+asyncmy://{_DB_USER}:{_DB_PASSWORD}@{host}:{port}/{_DB_NAME}"
