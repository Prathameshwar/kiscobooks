from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from billing_platform.testing import engine, factory, session, tenant_a, tenant_b  # noqa: F401
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog import models  # noqa: F401
from catalog.config import Settings
from catalog.main import create_app

ACTOR_SECRET = "ephemeral-catalog-test-key-not-a-live-secret"


@pytest.fixture
def app(engine: AsyncEngine) -> FastAPI:  # noqa: F811
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(ACTOR_SECRET),
        ),
        engine=engine,
    )


@pytest.fixture
def native_retirement(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    from voucher_execution.retirement_transport import RetirementClient, RetirementConnection

    from tests.stock_retirement_factories import NativeOwners

    owners = NativeOwners()
    connection = RetirementConnection(
        origin="http://127.0.0.1:8011",
        secret=SecretStr(ACTOR_SECRET),
    )
    app.state.settings = app.state.settings.model_copy(
        update={
            "stock_retirement_accounting": connection,
            "stock_retirement_vouchers": connection,
        }
    )

    async def check(client, request):
        return await owners.check(client.owner, request)

    async def release(client, request):
        owners.releases.append(request)

    monkeypatch.setattr(RetirementClient, "check", check)
    monkeypatch.setattr(RetirementClient, "release", release)
    return owners


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://catalog.test",
        ) as connection:
            yield connection


@pytest.fixture
def stable_product_source_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Workflow tests represent one authorization interval, even under slow coverage.

    Expiry/re-bootstrap tests keep real or explicitly advanced clocks. This fixture
    never changes production freshness windows or actor authorization behavior.
    """
    from types import SimpleNamespace

    from billing_platform import gateway
    from billing_platform.db.types import utcnow

    from catalog.tasks import actor_authorization, identity_source, projections
    from tests import bulk_factories, source_factories, test_actor_authorization, test_api

    instant = utcnow()
    actor_clock = SimpleNamespace(time=lambda: instant.timestamp())
    monkeypatch.setattr(gateway, "time", actor_clock)
    monkeypatch.setattr(test_api, "time", actor_clock)
    monkeypatch.setattr(identity_source, "utcnow", lambda: instant)
    monkeypatch.setattr(projections, "utcnow", lambda: instant)
    monkeypatch.setattr(source_factories, "utcnow", lambda: instant)
    monkeypatch.setattr(actor_authorization, "utcnow", lambda: instant)
    monkeypatch.setattr(bulk_factories, "utcnow", lambda: instant)
    # Proofs minted here must share the same instant: validate_proof compares them against
    # ``actor_authorization.utcnow`` above, which is pinned. Without this, ``proof.generated_at``
    # runs on the real wall clock and trips the +5s freshness guard once a slow full run has
    # queued the test long enough for real time to advance past the pinned instant.
    monkeypatch.setattr(test_actor_authorization, "utcnow", lambda: instant)


@pytest.fixture(autouse=True)
def coverage_command_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tracing needs headroom; normal and native workflows retain the 10-second limit.

    Coverage instrumentation can multiply coroutine/SQLAlchemy work enough to cancel
    a valid command and discard SQLite's in-memory connection. This changes only
    the test process's default while coverage is active. Explicit timeout tests,
    source freshness, actor expiry and all production defaults remain unchanged.
    """
    from types import FunctionType
    from typing import cast

    from billing_platform.idempotency import execute_idempotent
    from coverage import Coverage

    if Coverage.current() is not None:
        defaults = cast(FunctionType, execute_idempotent).__kwdefaults__
        assert defaults is not None
        monkeypatch.setitem(defaults, "timeout_seconds", 60)
