"""Run independently with python -m catalog.tasks.audit_publisher."""

from __future__ import annotations

import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.publisher_cli import arguments, operate
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from catalog.events.audit_contract import AUDIT_EVENTS


class AuditPublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False, min_length=1)
    audit_broker_url: SecretStr = Field(min_length=1)
    audit_broker_user: str = Field(min_length=1, max_length=200)
    audit_event_secret: SecretStr = Field(min_length=32)
    audit_event_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    audit_exchange: str = Field(default="platform.audit", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    audit_batch_limit: int = Field(default=50, ge=1, le=100)
    audit_timeout_seconds: int = Field(default=5, ge=1, le=30)
    audit_maximum_attempts: int = Field(default=12, ge=1, le=100)


def configuration(settings: AuditPublisherSettings) -> PublisherConfig:
    return PublisherConfig(
        database_url=settings.database_url,
        broker_url=settings.audit_broker_url.get_secret_value(),
        broker_user=settings.audit_broker_user,
        key_id=settings.audit_event_key_id,
        key=ServiceKey(
            "catalog",
            "audit",
            AUDIT_EVENTS,
            settings.audit_event_secret.get_secret_value().encode(),
        ),
        exchange=settings.audit_exchange,
        batch_limit=settings.audit_batch_limit,
        timeout_seconds=settings.audit_timeout_seconds,
        maximum_attempts=settings.audit_maximum_attempts,
    )


async def run(settings: AuditPublisherSettings) -> None:
    await run_publisher(configuration(settings))


def main() -> None:
    args = arguments(__doc__)
    try:
        settings = AuditPublisherSettings(_env_file=args.env_file)  # type: ignore[call-arg] # environment
        asyncio.run(
            operate(configuration(settings), args)
            if args.status or args.retry or args.dead_letters
            else run(settings)
        )
    except Exception as exc:
        raise SystemExit("Catalog audit worker failed: " + type(exc).__name__) from None


if __name__ == "__main__":
    main()
