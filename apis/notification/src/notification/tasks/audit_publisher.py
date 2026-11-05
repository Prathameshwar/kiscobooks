"""Authenticated notification audit delivery, with an explicit historical cutoff."""

from __future__ import annotations

import argparse
import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.service_auth import ServiceKey
from pydantic import AwareDatetime, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from notification.metadata import TABLES

AUDIT_EVENT_TYPES = frozenset(
    f"notification.{table}.{operation}"
    for table in TABLES - {"outbox", "processed_message"}
    for operation in ("created", "updated", "deleted")
)


class PublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOTIFICATION_AUDIT_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False, validation_alias="NOTIFICATION_DATABASE_URL")
    broker_url: SecretStr
    broker_user: str
    event_secret: SecretStr = Field(min_length=32)
    event_key_id: str = "notification.current"
    publish_after: AwareDatetime


async def run(settings: PublisherSettings) -> None:
    await run_publisher(
        PublisherConfig(
            database_url=settings.database_url,
            broker_url=settings.broker_url.get_secret_value(),
            broker_user=settings.broker_user,
            key_id=settings.event_key_id,
            key=ServiceKey(
                "notification",
                "audit",
                AUDIT_EVENT_TYPES,
                settings.event_secret.get_secret_value().encode(),
            ),
            exchange="platform.audit",
            maximum_attempts=12,
            occurred_after=settings.publish_after,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(PublisherSettings(_env_file=args.env_file)))  # type: ignore[call-arg] # environment file
