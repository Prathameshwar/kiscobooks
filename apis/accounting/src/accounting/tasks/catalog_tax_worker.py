"""Consume Catalog GST publications into the Accounting tax replica.

Run ``python -m accounting.tasks.catalog_tax_worker`` separately from the HTTP process.
Broker credentials and the Catalog event signing secret are deployment data.
"""

from __future__ import annotations

import asyncio
import logging

from billing_platform.broker import (
    BrokerSource,
    confirmed_channel,
    declare_consumer_queue,
    receive_one,
)
from billing_platform.db import create_engine, create_session_factory
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from accounting.schemas.catalog_tax_events import EVENT_TYPES
from accounting.tasks.catalog_tax_replica import CONSUMER, handle_catalog_tax

logger = logging.getLogger(__name__)


class CatalogTaxWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ACCOUNTING_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    catalog_broker_url: SecretStr
    catalog_broker_user: str = Field(min_length=1, max_length=200)
    catalog_event_secret: SecretStr = Field(min_length=32)
    catalog_event_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    catalog_exchange: str = Field(default="platform.sources", min_length=1, max_length=120)
    catalog_tax_queue: str = Field(default=CONSUMER, min_length=1, max_length=120)
    catalog_dead_exchange: str = Field(
        default="platform.source_errors", min_length=1, max_length=120
    )


def broker_source(settings: CatalogTaxWorkerSettings) -> BrokerSource:
    """Only Catalog, signing for Accounting, may publish these three contracts."""
    return BrokerSource(
        ServiceKey(
            "catalog",
            "accounting",
            EVENT_TYPES,
            settings.catalog_event_secret.get_secret_value().encode(),
        ),
        settings.catalog_broker_user,
    )


async def run(settings: CatalogTaxWorkerSettings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    sources = {settings.catalog_event_key_id: broker_source(settings)}
    try:
        while True:
            try:
                async with confirmed_channel(
                    settings.catalog_broker_url.get_secret_value()
                ) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name=settings.catalog_exchange,
                        queue_name=settings.catalog_tax_queue,
                        dead_letter_exchange=settings.catalog_dead_exchange,
                        routes=tuple(sorted(EVENT_TYPES)),
                        # One consumer at a time keeps publications in queue order; the
                        # generation check still makes any reordering harmless.
                        single_active_consumer=True,
                    )
                    async with queue.iterator() as messages:
                        async for message in messages:
                            await receive_one(
                                factory,
                                message,
                                sources=sources,
                                audience="accounting",
                                consumer_name=CONSUMER,
                                handler=handle_catalog_tax,
                            )
            except Exception as exc:
                logger.warning("Accounting Catalog tax worker retry: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(CatalogTaxWorkerSettings()))  # type: ignore[call-arg]  # settings read required environment


__all__ = ["CatalogTaxWorkerSettings", "broker_source", "run"]
