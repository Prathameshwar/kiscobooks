"""Publish voucher send commands to Notification through confirmed outbox delivery."""

import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.publisher_cli import arguments, operate
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOUCHERS_NOTIFICATION_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(validation_alias="VOUCHERS_DATABASE_URL", repr=False)
    broker_url: SecretStr
    broker_user: str = Field(min_length=1, max_length=200)
    secret: SecretStr = Field(min_length=32)
    key_id: str = Field(default="vouchers.current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")


def configuration(settings: Settings) -> PublisherConfig:
    return PublisherConfig(
        database_url=settings.database_url,
        broker_url=settings.broker_url.get_secret_value(),
        broker_user=settings.broker_user,
        key_id=settings.key_id,
        key=ServiceKey(
            "vouchers",
            "notification",
            frozenset({"notification.send", "vouchers.voucher.notification_state"}),
            settings.secret.get_secret_value().encode(),
        ),
        exchange="platform.notification",
        maximum_attempts=12,
    )


def main() -> None:
    args = arguments(__doc__)
    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # environment
    config = configuration(settings)
    asyncio.run(
        operate(config, args)
        if args.status or args.retry or args.dead_letters
        else run_publisher(config)
    )


if __name__ == "__main__":
    main()
