"""Optional messaging supervisor; each service supplies its own event contracts."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
import time
from dataclasses import dataclass, field

import aio_pika

from billing_platform.broker import ConfirmedPublisher, confirmed_channel
from billing_platform.db import create_engine, create_session_factory
from billing_platform.delivery import MAX_EVENT_TYPES, publish_batch
from billing_platform.outbox_ops import inventory
from billing_platform.service_auth import ServiceKey

logger = logging.getLogger(__name__)
_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,119}\Z")


@dataclass(frozen=True, slots=True)
class PublisherConfig:
    database_url: str = field(repr=False)
    broker_url: str = field(repr=False)
    broker_user: str
    key_id: str
    key: ServiceKey
    exchange: str
    batch_limit: int = 50
    timeout_seconds: int = 5
    idle_seconds: float = 1
    retry_seconds: float = 5
    maximum_attempts: int | None = None
    occurred_after: dt.datetime | None = None

    def __post_init__(self) -> None:
        if not self.database_url or not self.broker_url:
            raise ValueError("publisher connection settings are required")
        if not 1 <= len(self.broker_user) <= 200 or any(
            ord(char) < 32 for char in self.broker_user
        ):
            raise ValueError("publisher broker identity is required")
        if (
            not _NAME.fullmatch(self.key_id)
            or not 1 <= len(self.exchange) <= 120
            or any(ord(char) < 32 for char in self.exchange)
        ):
            raise ValueError("explicit publisher key and exchange names are required")
        if len(self.key.operations) > MAX_EVENT_TYPES:
            raise ValueError(f"publisher event allowlist exceeds {MAX_EVENT_TYPES} contracts")
        if type(self.batch_limit) is not int or not 1 <= self.batch_limit <= 100:
            raise ValueError("publisher batch limit must be between 1 and 100")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 30:
            raise ValueError("publisher timeout must be between 1 and 30 seconds")
        if not 0 < self.idle_seconds <= 60 or not 1 <= self.retry_seconds <= 60:
            raise ValueError("publisher polling delays must be bounded")
        if self.maximum_attempts is not None and (
            type(self.maximum_attempts) is not int or not 1 <= self.maximum_attempts <= 32767
        ):
            raise ValueError("invalid maximum publish attempts")
        if self.occurred_after is not None and self.occurred_after.tzinfo is None:
            raise ValueError("publication cutoff must include a timezone")


async def run_publisher(config: PublisherConfig) -> None:
    """Reconnect on failure and dispose on shutdown; never log connection secrets.

    Only key.operations are selected from the outbox. A missing queue binding or
    negative broker confirmation leaves the original message pending for retry.
    Consumers still have to acknowledge their own database commits independently.
    """
    engine = create_engine(config.database_url)
    factory = create_session_factory(engine)
    last_health = 0.0
    try:
        while True:
            try:
                async with confirmed_channel(config.broker_url) as channel:
                    exchange = await channel.declare_exchange(
                        config.exchange, aio_pika.ExchangeType.TOPIC, durable=True
                    )
                    publisher = ConfirmedPublisher(
                        exchange,
                        key_id=config.key_id,
                        key=config.key,
                        broker_user=config.broker_user,
                        timeout_seconds=config.timeout_seconds,
                    )
                    while True:
                        if time.monotonic() - last_health >= 60:
                            health = await inventory(
                                factory,
                                config.key.operations,
                                maximum_attempts=config.maximum_attempts or 32767,
                                occurred_after=config.occurred_after,
                                sample_limit=0,
                            )
                            if health["exhausted"] or health["oldest_age_seconds"] > 300:
                                logger.warning(
                                    "%s",
                                    json.dumps(
                                        {
                                            "event": "outbox.stalled",
                                            "service": config.key.issuer,
                                            "pending": health["pending"],
                                            "exhausted": health["exhausted"],
                                            "oldest_age_seconds": health["oldest_age_seconds"],
                                        },
                                        sort_keys=True,
                                    ),
                                )
                            last_health = time.monotonic()
                        result = await publish_batch(
                            factory,
                            publisher,
                            limit=config.batch_limit,
                            timeout_seconds=config.timeout_seconds,
                            event_types=config.key.operations,
                            maximum_attempts=config.maximum_attempts,
                            occurred_after=config.occurred_after,
                        )
                        if result.confirmed or result.deferred:
                            logger.info(
                                "%s outbox confirmed=%d deferred=%d",
                                config.key.issuer,
                                result.confirmed,
                                result.deferred,
                            )
                        if not result.confirmed:
                            await asyncio.sleep(config.idle_seconds)
            except Exception as exc:
                logger.warning("%s outbox retry: %s", config.key.issuer, type(exc).__name__)
                await asyncio.sleep(config.retry_seconds)
    finally:
        await engine.dispose()
