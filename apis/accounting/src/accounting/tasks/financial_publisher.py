"""Confirmed financial source delivery: python -m accounting.tasks.financial_publisher."""

import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from accounting.events.financial_contract import EVENT_TYPES


class FinancialPublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ACCOUNTING_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False, min_length=1)
    financial_broker_url: SecretStr
    financial_broker_user: str = Field(min_length=1, max_length=200)
    financial_event_secret: SecretStr = Field(min_length=32)
    financial_event_key_id: str = Field(
        default="accounting.current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$"
    )
    financial_exchange: str = Field(default="accounting.financial", min_length=1, max_length=120)


def configuration(settings: FinancialPublisherSettings) -> PublisherConfig:
    return PublisherConfig(
        database_url=settings.database_url,
        broker_url=settings.financial_broker_url.get_secret_value(),
        broker_user=settings.financial_broker_user,
        key_id=settings.financial_event_key_id,
        key=ServiceKey(
            "accounting",
            "financial-services",
            EVENT_TYPES,
            settings.financial_event_secret.get_secret_value().encode(),
        ),
        exchange=settings.financial_exchange,
    )


if __name__ == "__main__":
    # BaseSettings reads the required deployment credentials from environment variables.
    settings = FinancialPublisherSettings()  # type: ignore[call-arg]
    asyncio.run(run_publisher(configuration(settings)))
