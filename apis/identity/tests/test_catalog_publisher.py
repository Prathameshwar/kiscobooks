"""Supervisor unit tests; broker/DB roundtrips are separate integration gates."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from billing_platform.delivery import PublishResult
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from identity.tasks import catalog_publisher


async def test_publisher_reconnects_and_filters_only_catalog_sources(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
) -> None:
    attempts = 0
    batches = 0
    pauses = []

    class Channel:
        async def declare_exchange(self, *args: Any, **kwargs: Any) -> object:
            assert kwargs["durable"] is True
            return object()

    @asynccontextmanager
    async def channel(url: str) -> AsyncIterator[Channel]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary connect failure")
        yield Channel()

    async def publish(*args: Any, **kwargs: Any) -> PublishResult:
        nonlocal batches
        batches += 1
        assert kwargs["event_types"] == frozenset({catalog_publisher.EVENT_TYPE})
        if batches == 3:
            raise RuntimeError("transport disconnected")
        return PublishResult(confirmed=1 if batches == 1 else 0, deferred=0)

    async def pause(seconds: float) -> None:
        pauses.append(seconds)
        if pauses.count(5) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("billing_platform.publisher.create_engine", lambda url: engine)
    monkeypatch.setattr("billing_platform.publisher.confirmed_channel", channel)
    monkeypatch.setattr("billing_platform.publisher.publish_batch", publish)
    monkeypatch.setattr(asyncio, "sleep", pause)
    settings = catalog_publisher.PublisherSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        source_broker_url=SecretStr("amqp://ephemeral.invalid"),
        source_broker_user="identity",
        source_event_secret=SecretStr("ephemeral-event-key" * 3),
    )
    with pytest.raises(asyncio.CancelledError):
        await catalog_publisher.run(settings)
    assert batches == 3 and attempts == 2 and pauses == [5, 1, 5]
