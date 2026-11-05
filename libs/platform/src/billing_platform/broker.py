"""Optional aio-pika adapter for confirmed outbox and authenticated inbox delivery.

Install billing-platform[messaging]. Broker accounts must have publisher ACLs and
must not carry RabbitMQ's impersonator tag: RabbitMQ validates the user_id property.
HMAC keys also bind the issuer, audience, route and exact persisted message body.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractIncomingMessage
from pamqp.commands import Basic
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.delivery import OutgoingMessage, consume_once
from billing_platform.errors import AuthenticationRequiredError, ValidationFailedError
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import ServiceKey, sign_service_body, verify_service_body

# A shared consumer binds the union of several independently bounded source contracts.
MAX_CONSUMER_ROUTES = 4096


@dataclass(frozen=True, slots=True)
class BrokerSource:
    key: ServiceKey
    broker_user: str


class ConfirmedPublisher:
    def __init__(
        self,
        exchange: AbstractExchange,
        *,
        key_id: str,
        key: ServiceKey,
        broker_user: str,
        timeout_seconds: int = 5,
    ) -> None:
        if not broker_user or not 1 <= timeout_seconds <= 30:
            raise ValueError("publisher identity and bounded timeout required")
        self.exchange = exchange
        self.key_id, self.key = key_id, key
        self.broker_user, self.timeout = broker_user, timeout_seconds

    async def __call__(self, outgoing: OutgoingMessage) -> bool:
        issued = int(time.time())
        signature = sign_service_body(
            self.key,
            key_id=self.key_id,
            operation=outgoing.routing_key,
            timestamp=issued,
            body=outgoing.body,
        )
        message = aio_pika.Message(
            body=outgoing.body,
            message_id=str(outgoing.message_id),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            user_id=self.broker_user,
            type=outgoing.routing_key,
            headers={
                "key_id": self.key_id,
                "issuer": self.key.issuer,
                "audience": self.key.audience,
                "signed_at": str(issued),
                "signature": signature,
            },
        )
        confirmation = await self.exchange.publish(
            message,
            outgoing.routing_key,
            mandatory=True,
            timeout=self.timeout,
        )
        return isinstance(confirmation, Basic.Ack)


def authenticated_envelope(
    message: AbstractIncomingMessage,
    *,
    sources: Mapping[str, BrokerSource],
    audience: str,
) -> MessageEnvelope:
    headers = message.headers
    names = ("key_id", "issuer", "audience", "signed_at", "signature")
    if any(not isinstance(headers.get(name), str) for name in names):
        raise AuthenticationRequiredError("broker source authentication failed")
    values = {name: str(headers[name]) for name in names}
    source = sources.get(values["key_id"])
    if source is None or message.user_id != source.broker_user or values["audience"] != audience:
        raise AuthenticationRequiredError("broker source authentication failed")
    verify_service_body(
        {values["key_id"]: source.key},
        key_id=values["key_id"],
        issuer=values["issuer"],
        audience=audience,
        operation=message.routing_key or "",
        timestamp=values["signed_at"],
        signature=values["signature"],
        body=message.body,
        now=int(time.time()),
        maximum_age=None,
    )
    # Durable delivery can be delayed. Source version/freshness and inbox replay
    # controls, rather than gateway clock skew, govern acceptance of old events.
    envelope = MessageEnvelope.model_validate_json(message.body)
    if (
        message.message_id != str(envelope.message_id)
        or message.routing_key != envelope.event_type
        or message.type != envelope.event_type
        or message.content_type != "application/json"
        or envelope.schema_version != 1
    ):
        raise ValidationFailedError("broker envelope metadata does not match")
    return envelope


async def receive_one(
    factory: async_sessionmaker[AsyncSession],
    message: AbstractIncomingMessage,
    *,
    sources: Mapping[str, BrokerSource],
    audience: str,
    consumer_name: str,
    handler: Callable[[AsyncSession, MessageEnvelope], Awaitable[None]],
) -> None:
    """Commit before ACK. Invalid/domain-rejected events go to a durable DLQ.

    Transient exceptions propagate with delivery unacknowledged; the runner closes
    the channel and backs off. It must not spin on NACK/requeue on the same channel.
    """
    try:
        envelope = authenticated_envelope(message, sources=sources, audience=audience)
        await consume_once(factory, envelope, handler, consumer_name=consumer_name)
    except (AuthenticationRequiredError, ValidationFailedError, ValidationError):
        await message.reject(requeue=False)
        return
    await message.ack()


@asynccontextmanager
async def confirmed_channel(url: str) -> AsyncIterator[AbstractChannel]:
    """Both mandatory returns and missing confirms fail publication."""
    connection = await aio_pika.connect_robust(url, timeout=10)
    try:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        try:
            yield channel
        finally:
            await channel.close()
    finally:
        await connection.close()


async def declare_consumer_queue(
    channel: AbstractChannel,
    *,
    exchange_name: str,
    queue_name: str,
    dead_letter_exchange: str,
    routes: tuple[str, ...],
    prefetch: int = 20,
    single_active_consumer: bool = False,
) -> aio_pika.abc.AbstractQueue:
    if not routes or len(routes) > MAX_CONSUMER_ROUTES or not 1 <= prefetch <= 100:
        raise ValueError("bounded explicit routes and prefetch required")
    if any(not name for name in (exchange_name, queue_name, dead_letter_exchange)):
        raise ValueError("durable topology names required")
    if any("#" in route or "*" in route for route in routes):
        raise ValueError("source subscriptions must name exact event contracts")
    await channel.set_qos(prefetch_count=prefetch)
    exchange = await channel.declare_exchange(
        exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
    )
    dead = await channel.declare_exchange(
        dead_letter_exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )
    dead_queue = await channel.declare_queue(queue_name + ".dead", durable=True)
    await dead_queue.bind(dead, routing_key=queue_name)
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": dead_letter_exchange,
            "x-dead-letter-routing-key": queue_name,
            **({"x-single-active-consumer": True} if single_active_consumer else {}),
        },
    )
    for route in routes:
        await queue.bind(exchange, routing_key=route)
    return queue
