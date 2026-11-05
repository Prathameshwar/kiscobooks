import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pamqp.commands import Basic

from billing_platform import dead_letters
from billing_platform.errors import AuthenticationRequiredError
from billing_platform.publisher import PublisherConfig
from tests.test_broker import KEY, message


def setup(monkeypatch, items, confirmation=None):
    for item in items:
        item.routing_key = "dead"
        item.processed = False

        async def ack(current=item):
            current.processed = True

        item.ack = AsyncMock(side_effect=ack)
        item.nack = AsyncMock()
    queue = SimpleNamespace(
        declaration_result=SimpleNamespace(message_count=len(items)),
        get=AsyncMock(side_effect=items),
    )
    exchange = SimpleNamespace(publish=AsyncMock(return_value=confirmation or Basic.Ack()))
    channel = SimpleNamespace(
        declare_queue=AsyncMock(return_value=queue), get_exchange=AsyncMock(return_value=exchange)
    )

    @asynccontextmanager
    async def connect(url):
        yield channel

    monkeypatch.setattr(dead_letters, "confirmed_channel", connect)
    config = PublisherConfig(
        database_url="sqlite+aiosqlite:///:memory:",
        broker_url="amqp://test.invalid",
        broker_user="identity_publisher",
        key_id="current",
        key=KEY,
        exchange="test.events",
    )
    return config, exchange


async def test_inspection_reports_invalid_original_without_replaying_it(monkeypatch):
    valid, invalid = message(), message()
    invalid.body = b"{}"
    config, exchange = setup(monkeypatch, [valid, invalid])
    result = await dead_letters.recover_dead_letters(config, "test.dead", [])
    assert [r["verified"] for r in result] == [True, False]
    exchange.publish.assert_not_awaited()
    valid.nack.assert_awaited_once_with(requeue=True)
    invalid.nack.assert_awaited_once_with(requeue=True)


async def test_replay_preserves_original_and_waits_for_ack(monkeypatch):
    original = message()
    body, headers, mid = original.body, dict(original.headers), original.message_id
    config, exchange = setup(monkeypatch, [original])
    result = await dead_letters.recover_dead_letters(
        config, "test.dead", [uuid.UUID(mid)], apply=True
    )
    assert result[0]["applied"]
    sent = exchange.publish.call_args.args[0]
    assert (sent.body, sent.headers, sent.message_id) == (body, headers, mid)
    original.ack.assert_awaited_once()
    original.nack.assert_not_awaited()


async def test_replay_rejects_invalid_missing_or_unconfirmed_selection(monkeypatch):
    invalid = message()
    invalid.body = b"{}"
    config, exchange = setup(monkeypatch, [invalid])
    with pytest.raises(AuthenticationRequiredError):
        await dead_letters.recover_dead_letters(
            config, "test.dead", [uuid.UUID(invalid.message_id)], apply=True
        )
    exchange.publish.assert_not_awaited()
    original = message()
    config, _ = setup(monkeypatch, [original], Basic.Nack())
    with pytest.raises(RuntimeError):
        await dead_letters.recover_dead_letters(
            config, "test.dead", [uuid.UUID(original.message_id)], apply=True
        )
    original.ack.assert_not_awaited()
    original.nack.assert_awaited_once()
    config, _ = setup(monkeypatch, [message()])
    with pytest.raises(ValueError, match="not every"):
        await dead_letters.recover_dead_letters(config, "test.dead", [uuid.uuid4()], apply=True)


@pytest.mark.parametrize("ids,apply,limit", [([], True, 100), ([], False, 101), ([], False, 0)])
async def test_recovery_bounds(monkeypatch, ids, apply, limit):
    config, _ = setup(monkeypatch, [])
    with pytest.raises(ValueError):
        await dead_letters.recover_dead_letters(config, "test.dead", ids, apply=apply, limit=limit)
