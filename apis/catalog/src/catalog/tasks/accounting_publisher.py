"""Run independently with python -m catalog.tasks.accounting_publisher.

Publishes only Catalog's GST publications (``catalog.tax_*.changed``) to ``platform.sources``,
signed by Catalog for Accounting; Accounting's ``accounting.catalog_tax.v1`` queue binds them
(docs/tax-accounting-plan.md Phase 5). Audit events keep their own publisher and key.
"""

from __future__ import annotations

import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.publisher_cli import arguments, operate
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from catalog.events.tax_publication import AUDIENCE, TAX_PUBLICATION_EVENTS


class AccountingPublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False, min_length=1)
    source_broker_url: SecretStr = Field(min_length=1)
    source_broker_user: str = Field(min_length=1, max_length=200)
    accounting_event_secret: SecretStr = Field(min_length=32)
    accounting_event_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    source_exchange: str = Field(default="platform.sources", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    source_batch_limit: int = Field(default=50, ge=1, le=100)
    source_timeout_seconds: int = Field(default=5, ge=1, le=30)
    source_maximum_attempts: int = Field(default=12, ge=1, le=100)


def configuration(settings: AccountingPublisherSettings) -> PublisherConfig:
    return PublisherConfig(
        database_url=settings.database_url,
        broker_url=settings.source_broker_url.get_secret_value(),
        broker_user=settings.source_broker_user,
        key_id=settings.accounting_event_key_id,
        key=ServiceKey(
            "catalog",
            AUDIENCE,
            TAX_PUBLICATION_EVENTS,
            settings.accounting_event_secret.get_secret_value().encode(),
        ),
        exchange=settings.source_exchange,
        batch_limit=settings.source_batch_limit,
        timeout_seconds=settings.source_timeout_seconds,
        maximum_attempts=settings.source_maximum_attempts,
    )


async def run(settings: AccountingPublisherSettings) -> None:
    await run_publisher(configuration(settings))


def main() -> None:
    args = arguments(__doc__)
    try:
        settings = AccountingPublisherSettings(_env_file=args.env_file)  # type: ignore[call-arg] # environment
        asyncio.run(
            operate(configuration(settings), args)
            if args.status or args.retry or args.dead_letters
            else run(settings)
        )
    except Exception as exc:
        raise SystemExit("Catalog accounting publisher failed: " + type(exc).__name__) from None


if __name__ == "__main__":
    main()
