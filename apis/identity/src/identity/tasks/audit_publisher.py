"""python -m identity.tasks.audit_publisher; confirmed, signed audit delivery."""

from __future__ import annotations

import argparse
import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.service_auth import ServiceKey
from pydantic import AwareDatetime, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from identity.events.audit_contract import AUDIT_EVENT_TYPES


class PublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_AUDIT_",
        extra="ignore",
        hide_input_in_errors=True,
    )
    database_url: str = Field(repr=False, validation_alias="IDENTITY_DATABASE_URL")
    broker_url: SecretStr
    broker_user: str = Field(min_length=1, max_length=200)
    event_secret: SecretStr = Field(min_length=32)
    event_key_id: str = Field(default="identity.current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    exchange: str = Field(default="platform.audit", min_length=1, max_length=120)
    # Explicit rollout boundary: historical personal data needs reviewed remediation.
    publish_after: AwareDatetime
    maximum_attempts: int = Field(default=12, ge=1, le=100, strict=True)


def configuration(settings: PublisherSettings) -> PublisherConfig:
    return PublisherConfig(
        database_url=settings.database_url,
        broker_url=settings.broker_url.get_secret_value(),
        broker_user=settings.broker_user,
        key_id=settings.event_key_id,
        key=ServiceKey(
            "identity",
            "audit",
            AUDIT_EVENT_TYPES,
            settings.event_secret.get_secret_value().encode(),
        ),
        exchange=settings.exchange,
        maximum_attempts=settings.maximum_attempts,
        occurred_after=settings.publish_after,
    )


async def run(settings: PublisherSettings) -> None:
    await run_publisher(configuration(settings))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(PublisherSettings(_env_file=args.env_file)))  # type: ignore[call-arg]  # pydantic-settings runtime environment-file argument
