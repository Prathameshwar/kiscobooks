"""Transport unit tests plus real SQLite transaction/acknowledgement ordering."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aio_pika import DeliveryMode
from aio_pika.abc import AbstractExchange
from pamqp.commands import Basic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.broker import (
    BrokerSource,
    ConfirmedPublisher,
    authenticated_envelope,
    receive_one,
)
from billing_platform.db.platform_models import Outbox, ProcessedMessage
from billing_platform.db.types import utcnow
from billing_platform.delivery import OutgoingMessage
from billing_platform.errors import AuthenticationRequiredError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.outbox import emit
from billing_platform.service_auth import ServiceKey, sign_service_body

KEY = ServiceKey("identity", "catalog", frozenset({"company.snapshot"}), b"test-key-material" * 3)
SOURCES = {"current": BrokerSource(KEY, "identity_publisher")}


def message() -> Any:
    envelope = MessageEnvelope(
        message_id=uuid7(),
        tenant_id=uuid7(),
        event_type="company.snapshot",
        schema_version=1,
        occurred_at=utcnow(),
        payload={"source_version": 1},
    )
    body = envelope.model_dump_json().encode()
    signed = sign_service_body(
        KEY, key_id="current", operation=envelope.event_type, timestamp=1, body=body
    )
    return SimpleNamespace(
        body=body,
        headers={
            "key_id": "current",
            "issuer": "identity",
            "audience": "catalog",
            "signed_at": "1",
            "signature": signed,
        },
        user_id="identity_publisher",
        message_id=str(envelope.message_id),
        routing_key=envelope.event_type,
        type=envelope.event_type,
        content_type="application/json",
        ack=AsyncMock(),
        reject=AsyncMock(),
    )


async def test_publisher_requires_ack_and_durable_mandatory_properties() -> None:
    exchange = AsyncMock(spec=AbstractExchange)
    publisher = ConfirmedPublisher(
        exchange, key_id="current", key=KEY, broker_user="identity_publisher"
    )
    incoming = message()
    outgoing = OutgoingMessage(uuid7(), "company.snapshot", incoming.body)
    for result, accepted in [(Basic.Ack(), True), (Basic.Nack(), False), (None, False)]:
        exchange.publish.return_value = result
        assert await publisher(outgoing) is accepted
    sent = exchange.publish.call_args.args[0]
    assert sent.delivery_mode == DeliveryMode.PERSISTENT
    assert sent.user_id == "identity_publisher" and sent.message_id == str(outgoing.message_id)
    assert exchange.publish.call_args.kwargs == {"mandatory": True, "timeout": 5}
    with pytest.raises(ValueError):
        ConfirmedPublisher(exchange, key_id="current", key=KEY, broker_user="")


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_id", "other"),
        ("message_id", "other"),
        ("routing_key", "other"),
        ("type", "other"),
        ("content_type", "text/plain"),
        ("body", b"{}"),
    ],
)
def test_broker_and_signed_envelope_bindings(field: str, value: Any) -> None:
    incoming = message()
    setattr(incoming, field, value)
    with pytest.raises((AuthenticationRequiredError, ValidationFailedError)):
        authenticated_envelope(incoming, sources=SOURCES, audience="catalog")


def test_durable_age_and_required_source_headers() -> None:
    incoming = message()
    assert authenticated_envelope(incoming, sources=SOURCES, audience="catalog").schema_version == 1
    incoming.headers["audience"] = "reports"
    with pytest.raises(AuthenticationRequiredError):
        authenticated_envelope(incoming, sources=SOURCES, audience="catalog")
    incoming.headers = {}
    with pytest.raises(AuthenticationRequiredError):
        authenticated_envelope(incoming, sources=SOURCES, audience="catalog")


async def test_ack_observes_commit_duplicate_has_one_effect_and_failure_rolls_back(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    incoming = message()
    calls = 0
    fail = False

    async def handler(db: AsyncSession, envelope: MessageEnvelope) -> None:
        nonlocal calls
        calls += 1
        emit(
            db,
            aggregate_type="test",
            aggregate_id=uuid7(),
            tenant_id=envelope.tenant_id,
            event_type="test.applied",
            payload={},
        )
        await db.flush()
        if fail:
            raise RuntimeError("transient failure")

    async def acknowledged() -> None:
        async with factory() as check:
            assert len(list(await check.scalars(select(Outbox)))) == 1

    incoming.ack.side_effect = acknowledged
    for _ in range(2):
        await receive_one(
            factory,
            incoming,
            sources=SOURCES,
            audience="catalog",
            consumer_name="catalog.source",
            handler=handler,
        )
    assert calls == 1 and incoming.ack.await_count == 2
    fail = True
    incoming = message()
    with pytest.raises(RuntimeError):
        await receive_one(
            factory,
            incoming,
            sources=SOURCES,
            audience="catalog",
            consumer_name="catalog.source",
            handler=handler,
        )
    incoming.ack.assert_not_awaited()
    incoming.reject.assert_not_awaited()
    async with factory() as check:
        assert len(list(await check.scalars(select(Outbox)))) == 1
        assert len(list(await check.scalars(select(ProcessedMessage)))) == 1
    incoming.user_id = "untrusted"
    await receive_one(
        factory,
        incoming,
        sources=SOURCES,
        audience="catalog",
        consumer_name="catalog.source",
        handler=handler,
    )
    incoming.reject.assert_awaited_once_with(requeue=False)


async def test_confirmed_channel_and_durable_dlq_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    from billing_platform.broker import confirmed_channel, declare_consumer_queue

    connection, channel, queue = AsyncMock(), AsyncMock(), AsyncMock()
    connection.channel.return_value = channel
    channel.declare_queue.return_value = queue
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr("billing_platform.broker.aio_pika.connect_robust", connect)
    async with confirmed_channel("amqp://test.invalid") as opened:
        assert opened is channel
        result = await declare_consumer_queue(
            channel,
            exchange_name="events",
            queue_name="catalog.source",
            dead_letter_exchange="dead",
            routes=("company.snapshot",),
        )
        assert result is queue
    connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    channel.close.assert_awaited_once()
    connection.close.assert_awaited_once()
    assert channel.declare_queue.call_args.kwargs["arguments"]["x-dead-letter-exchange"] == "dead"
    bad_settings: list[dict[str, Any]] = [
        {"routes": ()},
        {"prefetch": 101},
        {"exchange_name": ""},
        {"routes": ("company.#",)},
    ]
    for changes in bad_settings:
        with pytest.raises(ValueError):
            await declare_consumer_queue(
                channel,
                **{
                    "exchange_name": "events",
                    "queue_name": "source",
                    "dead_letter_exchange": "dead",
                    "routes": ("company.snapshot",),
                    **changes,
                },
            )


async def test_invalid_payload_goes_to_dlq_without_handler(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    incoming = message()
    incoming.body = b"{}"
    incoming.headers["signature"] = sign_service_body(
        KEY, key_id="current", operation="company.snapshot", timestamp=1, body=incoming.body
    )
    handler = AsyncMock()
    await receive_one(
        factory,
        incoming,
        sources=SOURCES,
        audience="catalog",
        consumer_name="catalog.source",
        handler=handler,
    )
    incoming.reject.assert_awaited_once_with(requeue=False)
    handler.assert_not_awaited()


@pytest.mark.parametrize("count", (105, 1024, 1115, 4096))
async def test_consumer_binds_large_exact_registry_with_bounded_prefetch(count: int) -> None:
    from billing_platform.broker import declare_consumer_queue

    channel, dead, queue = AsyncMock(), AsyncMock(), AsyncMock()
    channel.declare_queue.side_effect = [dead, queue]
    routes = tuple(f"test.event{i}" for i in range(count))
    result = await declare_consumer_queue(
        channel,
        exchange_name="events",
        queue_name="audit.events",
        dead_letter_exchange="dead",
        routes=routes,
        prefetch=20,
    )
    assert result is queue
    channel.set_qos.assert_awaited_once_with(prefetch_count=20)
    assert tuple(call.kwargs["routing_key"] for call in queue.bind.await_args_list) == routes
    untouched = AsyncMock()
    with pytest.raises(ValueError):
        await declare_consumer_queue(
            untouched,
            exchange_name="events",
            queue_name="audit.events",
            dead_letter_exchange="dead",
            routes=tuple(f"test.event{i}" for i in range(4097)),
        )
    untouched.set_qos.assert_not_awaited()
