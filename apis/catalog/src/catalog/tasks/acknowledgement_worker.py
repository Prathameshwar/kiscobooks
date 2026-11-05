"""Ingesting trusted consumers' policy acknowledgements from signed source events.

Run ``python -m catalog.tasks.acknowledgement_worker`` separately from the HTTP process.
Credentials and the bounded tenant/company subscription list are deployment data.

A separate worker from ``source_worker`` on purpose. That one consumes Identity's company
context; this one consumes a *different producer* under a different HMAC secret, and one process
binding both keys would make a compromise of either secret a compromise of both flows
(CLAUDE.md §5.12). Two queues also fail independently: an acknowledgement backlog must not stall
the company-context lease every read depends on.

**Which service is speaking is never taken from the payload.** This worker binds exactly one
source key, so only the holder of Billing's secret can produce a message it accepts, and the
``consumer`` written on the row is that verified issuer. ``schemas/acknowledgements`` has no
``consumer`` field at all, so there is no path by which a message could name a different one.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Mapping

from aio_pika.abc import AbstractQueue
from billing_platform.broker import (
    BrokerSource,
    confirmed_channel,
    declare_consumer_queue,
    receive_one,
)
from billing_platform.db import create_engine, create_session_factory
from billing_platform.errors import ValidationFailedError
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import CompanyServiceScope as Subscription
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.policy_release import CONSUMERS
from catalog.schemas.acknowledgements import CONTRACT_VERSION, AcknowledgementEvent
from catalog.tasks.acknowledgements import ingest

#: The one producer this worker trusts, and therefore the one ``consumer`` value it can write.
#: Asserted against the domain catalogue so a rename in one place cannot leave the other
#: writing a value the schema's check constraint would reject at 3am.
PRODUCER = "billing"
assert PRODUCER in CONSUMERS
EVENT_TYPE = "billing.catalog_policy_release.acknowledged"
CONSUMER_NAME = "catalog.policy_acknowledgement.v1"
logger = logging.getLogger(__name__)


class AcknowledgementSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    #: The same bounded tenant/company grant the source worker uses: an acknowledgement about a
    #: company Catalog was not deployed to serve is refused rather than stored.
    source_subscriptions: tuple[Subscription, ...] = Field(min_length=1, max_length=1000)
    ack_broker_url: SecretStr
    ack_broker_user: str = Field(min_length=1, max_length=200)
    ack_event_secret: SecretStr = Field(min_length=32)
    ack_event_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    ack_exchange: str = Field(default="platform.sources", min_length=1, max_length=120)
    ack_queue: str = Field(default="catalog.policy_acknowledgement", min_length=1, max_length=120)
    ack_dead_exchange: str = Field(default="platform.source_errors", min_length=1, max_length=120)


def subscribed(subscriptions: tuple[Subscription, ...]) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    """The deployment's tenant → companies grant, as ``ingest`` checks it."""
    grant: dict[uuid.UUID, set[uuid.UUID]] = {}
    for scope in subscriptions:
        grant.setdefault(scope.tenant_id, set()).add(scope.company_id)
    return {tenant: frozenset(companies) for tenant, companies in grant.items()}


async def handle_acknowledgement(
    db: AsyncSession,
    envelope: MessageEnvelope,
    *,
    companies: Mapping[uuid.UUID, frozenset[uuid.UUID]],
) -> None:
    """Validate the envelope against the subscription and contract, then apply the claim.

    The contract version is pinned rather than negotiated. A consumer speaking a version Catalog
    does not know is dead-lettered: guessing at an unknown payload would be guessing about the
    one fact that stops Catalog reporting a policy as pending.
    """
    if (
        envelope.tenant_id not in companies
        or envelope.event_type != EVENT_TYPE
        or envelope.schema_version != CONTRACT_VERSION
    ):
        raise ValidationFailedError("acknowledgement is outside the configured subscription")
    event = AcknowledgementEvent.model_validate(envelope.payload)
    if event.tenant_id != envelope.tenant_id:
        raise ValidationFailedError("acknowledgement payload and envelope scopes differ")
    await ingest(
        db,
        message_id=envelope.message_id,
        consumer=PRODUCER,
        event=event,
        companies=companies,
    )


async def run(settings: AcknowledgementSettings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    companies = subscribed(settings.source_subscriptions)
    source = BrokerSource(
        ServiceKey(
            PRODUCER,
            "catalog",
            frozenset({EVENT_TYPE}),
            settings.ack_event_secret.get_secret_value().encode(),
        ),
        settings.ack_broker_user,
    )

    async def handler(db: AsyncSession, envelope: MessageEnvelope) -> None:
        await handle_acknowledgement(db, envelope, companies=companies)

    try:
        while True:
            try:
                async with confirmed_channel(settings.ack_broker_url.get_secret_value()) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name=settings.ack_exchange,
                        queue_name=settings.ack_queue,
                        dead_letter_exchange=settings.ack_dead_exchange,
                        routes=(EVENT_TYPE,),
                    )

                    async def consume(bound_queue: AbstractQueue = queue) -> None:
                        async with bound_queue.iterator() as messages:
                            async for message in messages:
                                await receive_one(
                                    factory,
                                    message,
                                    sources={settings.ack_event_key_id: source},
                                    audience="catalog",
                                    consumer_name=CONSUMER_NAME,
                                    handler=handler,
                                )

                    await consume()
            except Exception as exc:
                logger.warning("Catalog acknowledgement worker retry: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(AcknowledgementSettings()))  # type: ignore[call-arg]  # settings read env


__all__ = [
    "CONSUMER_NAME",
    "EVENT_TYPE",
    "PRODUCER",
    "AcknowledgementSettings",
    "handle_acknowledgement",
    "run",
    "subscribed",
]
