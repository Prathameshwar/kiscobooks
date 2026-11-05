"""Run with python -m identity.tasks.catalog_publisher; publishes only native source events."""

from __future__ import annotations

import argparse
import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EVENT_TYPE = "identity.catalog_context.changed"


class PublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    source_broker_url: SecretStr
    source_broker_user: str = Field(min_length=1, max_length=200)
    source_event_secret: SecretStr = Field(min_length=32)
    source_event_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    source_exchange: str = Field(default="platform.sources", min_length=1, max_length=120)


async def run(settings: PublisherSettings) -> None:
    await run_publisher(
        PublisherConfig(
            database_url=settings.database_url,
            broker_url=settings.source_broker_url.get_secret_value(),
            broker_user=settings.source_broker_user,
            key_id=settings.source_event_key_id,
            key=ServiceKey(
                "identity",
                "catalog",
                frozenset({EVENT_TYPE}),
                settings.source_event_secret.get_secret_value().encode(),
            ),
            exchange=settings.source_exchange,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(PublisherSettings(_env_file=args.env_file)))  # type: ignore[call-arg] # env file
