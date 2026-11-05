from __future__ import annotations

import asyncio
from typing import Any

import pytest
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.tasks import index_worker
from tests.test_identity_source_client import settings as source_settings


def configuration() -> index_worker.IndexWorkerSettings:
    return index_worker.IndexWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=source_settings(),
        source_subscriptions=(CompanyServiceScope(tenant_id=uuid7(), company_id=uuid7()),),
    )


async def test_worker_retries_traversal_failure_and_disposes_on_shutdown(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(index_worker, "create_engine", lambda url: engine)
    original = AsyncEngine.dispose
    disposed = 0

    async def dispose(instance: AsyncEngine, close: bool = True) -> None:
        nonlocal disposed
        if instance is engine:
            disposed += 1
        await original(instance, close=close)

    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    calls = 0

    async def run(*args: Any, **kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary storage failure")
        raise asyncio.CancelledError

    async def sleep(seconds: float) -> None:
        assert seconds == 3

    monkeypatch.setattr(index_worker, "run_once", run)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await index_worker.serve(configuration())
    assert calls == 2 and disposed == 1


def test_worker_entrypoint_loads_namespaced_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    config = configuration()
    monkeypatch.setattr(index_worker, "IndexWorkerSettings", lambda: config)

    async def serve(value: index_worker.IndexWorkerSettings) -> None:
        assert value is config

    monkeypatch.setattr(index_worker, "serve", serve)
    index_worker.main()


def test_worker_module_entrypoint_uses_environment_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import runpy
    from collections.abc import Coroutine
    from pathlib import Path

    config = configuration()
    monkeypatch.setenv("CATALOG_DATABASE_URL", config.database_url)
    monkeypatch.setenv(
        "CATALOG_IDENTITY_SOURCE",
        json.dumps(
            {
                "base_url": "http://127.0.0.1",
                "request_secret": "ephemeral-request-key-for-worker-test",
                "response_secrets": {"current": "ephemeral-response-key-for-worker-test"},
            }
        ),
    )
    monkeypatch.setenv(
        "CATALOG_SOURCE_SUBSCRIPTIONS",
        json.dumps([item.model_dump(mode="json") for item in config.source_subscriptions]),
    )
    called = False

    def run(coroutine: Coroutine[Any, Any, None]) -> None:
        nonlocal called
        called = True
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", run)
    runpy.run_path(str(Path(index_worker.__file__)), run_name="__main__")
    assert called
