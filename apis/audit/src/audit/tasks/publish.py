"""Deliver Audit export evidence through the same confirmed outbox mechanism."""

import asyncio

from billing_platform.publisher import PublisherConfig, run_publisher
from billing_platform.publisher_cli import arguments, operate
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDIT_PUBLISHER_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False, min_length=1)
    broker_url: SecretStr
    broker_user: str = Field(min_length=1)
    event_secret: SecretStr = Field(min_length=32)
    key_id: str = "audit.current"
    exchange: str = "platform.audit"

    def configuration(self) -> PublisherConfig:
        return PublisherConfig(
            database_url=self.database_url,
            broker_url=self.broker_url.get_secret_value(),
            broker_user=self.broker_user,
            key_id=self.key_id,
            key=ServiceKey(
                "audit",
                "audit",
                frozenset({"audit.exported"}),
                self.event_secret.get_secret_value().encode(),
            ),
            exchange=self.exchange,
            maximum_attempts=12,
        )


def main() -> None:
    args = arguments(__doc__)
    try:
        settings = PublisherSettings(_env_file=args.env_file)  # type: ignore[call-arg] # environment
        config = settings.configuration()
        asyncio.run(
            operate(config, args)
            if args.status or args.retry or args.dead_letters
            else run_publisher(config)
        )
    except Exception as exc:
        raise SystemExit("Audit export worker failed: " + type(exc).__name__) from None


if __name__ == "__main__":
    main()
