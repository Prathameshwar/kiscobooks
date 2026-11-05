"""Suite wiring for `notification`.

Session fixtures come from ``billing_platform.testing`` (SQLite, dialect-independent) so
every service builds a session the same way. The MySQL 9.6 container backs the
``@mysql``-marked tests (migration round-trip, dialect behaviour) and is skipped when no
container runtime is reachable — an unmet prerequisite, not a failure.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
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
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Registers every model on Base.metadata before `create_all` in the shared fixtures.
from notification import models  # noqa: F401
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET, DATA_KEY

#: MySQL 9.6 — the production engine (tech-stack.md decision log, 2026-09-11).
MYSQL_IMAGE = "mysql:9.6"

_DB_NAME = "notification"
_DB_USER = "notification"
# Throwaway credential for an ephemeral container on a random localhost port (§5.9).
_DB_PASSWORD = "test-only-not-a-secret"


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        done = subprocess.run(  # noqa: S603  fixed argv, no shell
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("NOTIFICATION_TEST_MYSQL_SERVER") or _docker_available():
        return
    skip = pytest.mark.skip(reason="no reachable container runtime; MySQL tests need Docker")
    for item in items:
        if "mysql" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def app(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], tenant_a) -> object:  # noqa: F811
    """The FastAPI app wired to the test's own SQLite engine (StaticPool, one DB)."""
    from notification.config import Settings
    from notification.main import create_app

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=ACTOR_SECRET,  # type: ignore[arg-type]
        cursor_signing_secret=CURSOR_SECRET,  # type: ignore[arg-type]
        data_encryption_key=DATA_KEY,  # type: ignore[arg-type]
    )
    from notification.config import CredentialBinding

    settings.credential_bindings = {
        f"env:{name}": CredentialBinding(
            tenant_id=tenant_a,
            space_id=tenant_a,
            environment_variable=name,
            allowed_senders=["noreply@acme.example"],
        )
        for name in ("PRIVATE", "VERIFY", "REVIEW", "SES")
    }
    from notification.config import OwnershipBinding
    from tests.sns_fixture import TOPIC, certificate

    settings.sns_topic_bindings = {TOPIC: OwnershipBinding(tenant_id=tenant_a, space_id=tenant_a)}
    settings.callback_public_origin = "http://notification.test"
    settings.credential_bindings["env:NOTIF_TEST_CB_SECRET"] = CredentialBinding(
        tenant_id=tenant_a, space_id=tenant_a, environment_variable="NOTIF_TEST_CB_SECRET"
    )
    application = create_app(settings)
    application.state.sns_certificate_loader = certificate
    application.state.engine = engine
    application.state.session_factory = factory
    return application


@pytest_asyncio.fixture
async def client(app: object) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://notification.test") as c:
        yield c


@pytest.fixture(scope="session")
def mysql_url() -> Iterator[str]:
    """An async URL for a throwaway MySQL 9.6, one container per test session."""
    native = os.environ.get("NOTIFICATION_TEST_MYSQL_SERVER")
    if native:
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import create_async_engine

        server = make_url(native).set(database=None)
        database = "notification_test_" + uuid.uuid4().hex

        async def schema(create: bool) -> None:
            engine = create_async_engine(server, echo=False)
            try:
                async with engine.connect() as conn:
                    command = (
                        f"CREATE DATABASE {database} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        if create
                        else f"DROP DATABASE {database}"
                    )
                    await conn.execute(text(command))
            finally:
                await engine.dispose()

        asyncio.run(schema(True))
        try:
            yield server.set(database=database).render_as_string(hide_password=False)
        finally:
            asyncio.run(schema(False))
        return
    from testcontainers.mysql import MySqlContainer

    container = MySqlContainer(
        image=MYSQL_IMAGE, username=_DB_USER, password=_DB_PASSWORD, dbname=_DB_NAME
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"mysql+asyncmy://{_DB_USER}:{_DB_PASSWORD}@{host}:{port}/{_DB_NAME}"
