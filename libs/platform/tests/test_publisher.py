"""Supervisor recovery uses the real outbox DB and a controllable broker boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aio_pika.abc import AbstractChannel, AbstractExchange
from pamqp.commands import Basic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from billing_platform import publisher
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.service_auth import ServiceKey

KEY = ServiceKey("test", "audit", frozenset({"test.changed"}), b"ephemeral-test-key" * 3)
CONFIG = PublisherConfig(
    "sqlite+aiosqlite:///:memory:", "amqp://test.invalid", "test", "current", KEY, "test.audit"
)


@pytest.mark.parametrize(
    "changes",
    [
        {"database_url": ""},
        {"broker_url": ""},
        {"broker_user": ""},
        {"broker_user": "user\n"},
        {"key_id": "invalid key"},
        {"exchange": ""},
        {"batch_limit": True},
        {"batch_limit": 101},
        {"timeout_seconds": True},
        {"timeout_seconds": 31},
        {"idle_seconds": float("nan")},
        {"retry_seconds": 0},
        {"key": replace(KEY, operations=frozenset(f"test.event{i}" for i in range(1025)))},
    ],
    ids=[
        "db",
        "broker",
        "user",
        "control",
        "key",
        "exchange",
        "bool-batch",
        "batch",
        "bool-timeout",
        "timeout",
        "idle",
        "retry",
        "routes",
    ],
)
def test_publisher_rejects_unbounded_or_missing_config(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(CONFIG, **changes)


def test_publisher_config_repr_hides_credentials() -> None:
    settings = replace(CONFIG, database_url="private-db-connection", broker_url="private-broker")
    assert "private-db-connection" not in repr(settings)
    assert "private-broker" not in repr(settings)
    assert KEY.secret.decode() not in repr(settings)


@pytest.mark.parametrize("count", (105, 1024))
def test_publisher_accepts_large_explicit_contract_registry(count: int) -> None:
    key = replace(KEY, operations=frozenset(f"test.event{i}" for i in range(count)))
    configured = replace(CONFIG, key=key)
    assert configured.key.operations == key.operations and configured.batch_limit == 50


async def test_confirmed_worker_reconnects_filters_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory.begin() as db:
        for event_type in ("test.changed", "unrelated.changed"):
            emit(
                db,
                aggregate_type="test",
                aggregate_id=uuid7(),
                tenant_id=uuid7(),
                event_type=event_type,
                payload={},
                occurred_at=utcnow() - timedelta(minutes=10),
            )
    exchange = AsyncMock(spec=AbstractExchange)
    exchange.publish.return_value = Basic.Ack()
    channel = AsyncMock(spec=AbstractChannel)
    channel.declare_exchange.return_value = exchange
    attempts = 0
    delays: list[float] = []
    disposed = False
    original_dispose = AsyncEngine.dispose

    async def dispose(instance: AsyncEngine, close: bool = True) -> None:
        nonlocal disposed
        disposed = True
        await original_dispose(instance, close=close)

    @asynccontextmanager
    async def connect(url: str) -> AsyncIterator[AbstractChannel]:
        nonlocal attempts
        attempts += 1
        assert url == CONFIG.broker_url
        if attempts == 1:
            raise RuntimeError("private-broker-credentials")
        yield channel

    async def pause(delay: float) -> None:
        delays.append(delay)
        if delay == CONFIG.idle_seconds:
            async with factory() as db:
                rows = list(await db.scalars(select(Outbox).order_by(Outbox.event_type)))
                assert rows[0].published_at is not None and rows[0].attempt_count == 1
                assert rows[1].published_at is None and rows[1].attempt_count == 0
            raise asyncio.CancelledError

    monkeypatch.setattr(publisher, "create_engine", lambda url: engine)
    monkeypatch.setattr(publisher, "confirmed_channel", connect)
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    monkeypatch.setattr(asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        await run_publisher(CONFIG)
    assert attempts == 2 and delays == [5, 1] and disposed
    assert "private-broker-credentials" not in caplog.text
    assert "RuntimeError" in caplog.text
    health = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]
    assert len(health) == 1 and health[0]["event"] == "outbox.stalled"
    assert health[0]["pending"] == 1 and health[0]["service"] == "test"
    assert "private" not in str(health)
    sent = exchange.publish.call_args.args[0]
    assert sent.type == "test.changed" and sent.user_id == "test"
    assert exchange.publish.call_args.kwargs["mandatory"] is True
