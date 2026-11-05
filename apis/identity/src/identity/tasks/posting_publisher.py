"""Publish confirmed reservation outcomes for Billing inbox consumers."""

from __future__ import annotations

import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EVENTS = frozenset({"identity.posting_reservation.terminal"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_POSTING_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(validation_alias="IDENTITY_DATABASE_URL", repr=False)
    broker_url: SecretStr
    broker_user: str = Field(min_length=1, max_length=200)
    secret: SecretStr = Field(min_length=32)
    key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")


async def run(settings: Settings) -> None:
    await run_publisher(
        PublisherConfig(
            database_url=settings.database_url,
            broker_url=settings.broker_url.get_secret_value(),
            broker_user=settings.broker_user,
            key_id=settings.key_id,
            key=ServiceKey(
                "identity", "billing", EVENTS, settings.secret.get_secret_value().encode()
            ),
            exchange="platform.billing",
            maximum_attempts=12,
        )
    )


if __name__ == "__main__":
    asyncio.run(run(Settings()))  # type: ignore[call-arg]  # required settings come from environment
