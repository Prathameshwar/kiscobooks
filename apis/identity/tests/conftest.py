"""Suite wiring for `identity`.

The session fixtures come from ``billing_platform.testing`` so seven service
suites share one definition of how a session is built. What is added here is the
MySQL container, because dialect behaviour — collation, DECIMAL truncation,
NULL-in-UNIQUE — is the whole reason the migration tests exist and none of it
reproduces on SQLite.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

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
from identity import models  # noqa: F401
from tests.alembic_support import docker_available
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET

#: MySQL 9.6 — the production version (tech-stack.md decision log, 2026-09-11). A
#: migration that passes on a different major has proven nothing about the one it will
#: run against.
MYSQL_IMAGE = "mysql:9.6"

_DB_NAME = "identity"
_DB_USER = "identity"
# Not a secret: a throwaway credential for an ephemeral container that binds to a
# random localhost port and is destroyed with the session (CLAUDE.md §5.9).
_DB_PASSWORD = "test-only-not-a-secret"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip container tests when no runtime is reachable, rather than erroring.

    An unavailable Docker is an unmet prerequisite, not a failing assertion, and
    conflating the two hides real failures.
    """
    if os.environ.get("IDENTITY_TEST_MYSQL_URL") or docker_available():
        return
    skip = pytest.mark.skip(reason="no reachable container runtime; MySQL tests need Docker")
    for item in items:
        if "mysql" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def app(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> object:  # noqa: F811
    """The FastAPI app wired to the test's own SQLite engine.

    ``create_app`` builds its own engine from the (unused) SQLite URL; we replace both
    ``engine`` and ``session_factory`` with the test's so a request sees exactly the
    rows the test seeded — one in-memory database, shared connection (StaticPool).
    """
    from identity.config import Settings
    from identity.main import create_app

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=ACTOR_SECRET,  # type: ignore[arg-type]
        cursor_signing_secret=CURSOR_SECRET,  # type: ignore[arg-type]
        public_auth_url="https://auth.test",
        # This is the Authentik-flavoured installation every older suite was written against; the
        # provider default is `local`, exercised by the `local_app` fixture below.
        auth_provider="authentik",
    )
    application = create_app(settings)
    application.state.engine = engine
    application.state.session_factory = factory
    return application


@pytest_asyncio.fixture
async def client(app: object) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://identity.test") as c:
        yield c


@pytest.fixture(scope="session")
def mysql_url() -> Iterator[str]:
    """An async URL for a throwaway MySQL 9.6, one container per test session."""
    # Explicit opt-in: this URL must name an empty disposable test database.
    local_url = os.environ.get("IDENTITY_TEST_MYSQL_URL")
    if local_url:
        yield local_url
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


# --- local authentication provider (docs/local-auth.md) -----------------------------------------


@pytest.fixture(autouse=True)
def _cheap_password_hashing() -> Iterator[None]:
    """argon2id at production cost is ~100 ms a hash; tests need the algorithm, not the price."""
    from identity.local_auth import domain

    domain.configure_hashing(domain.HashParameters(time_cost=1, memory_kib=8, parallelism=1))
    yield
    domain.configure_hashing(domain.HashParameters())


_RSA_BASE: dict[str, object] = {}


@pytest.fixture(autouse=True)
def _fast_signing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generating a 2048-bit RSA key takes a second; tests reuse one key under fresh key ids."""
    from joserfc.jwk import RSAKey

    if not _RSA_BASE:
        _RSA_BASE.update(RSAKey.generate_key(2048).as_dict(private=True))

    def generate(
        key_size: int = 2048, parameters: dict[str, str] | None = None, **_: object
    ) -> RSAKey:
        return RSAKey.import_key({**_RSA_BASE, **(parameters or {})})

    monkeypatch.setattr(RSAKey, "generate_key", staticmethod(generate))


@pytest.fixture(scope="session")
def _local_app_template() -> object:
    """``create_app`` costs seconds (route table, registry checks), so it runs once per session."""
    from identity.config import Settings
    from identity.main import create_app
    from tests.local_auth_support import local_settings

    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=ACTOR_SECRET,  # type: ignore[arg-type]
            cursor_signing_secret=CURSOR_SECRET,  # type: ignore[arg-type]
            public_auth_url="https://auth.test",
            auth_provider="local",
            local_auth=local_settings(),
        )
    )


@pytest.fixture
def local_app(
    _local_app_template: Any,
    engine: AsyncEngine,  # noqa: F811
    factory: async_sessionmaker[AsyncSession],  # noqa: F811
) -> object:
    """The app with the local provider on, wired to the test's own SQLite engine.

    Everything that holds per-test state is rebuilt here — the provider (it caches the decrypted
    signing key), the verifier (it caches the key set) and the throttle windows — so tests cannot
    see one another. The verifier fetches keys from the app itself over an in-process transport,
    so a token the provider issues is checked by the real ``AccessTokenVerifier``.
    """
    from billing_platform.oidc import AccessTokenVerifier
    from billing_platform.rate_limit import WindowLimiter

    from identity.local_auth.service import LocalAuth

    application = _local_app_template
    settings = application.state.settings
    application.state.engine = engine
    application.state.session_factory = factory
    application.state.auth_limiter = WindowLimiter()
    application.state.local_limiter = WindowLimiter()
    application.state.local_auth = LocalAuth(settings.local_auth)
    application.state.oidc_http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://localhost"
    )
    application.state.token_verifier = AccessTokenVerifier(
        settings.oidc.configuration(), application.state.oidc_http
    )
    return application


@pytest_asyncio.fixture
async def local_client(local_app: object) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=local_app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c
