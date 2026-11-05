"""Runtime configuration for the `audit` service.

Secrets arrive from the environment or a secret manager, never the repo
(CLAUDE.md §5.9). ``env_prefix`` namespaces every service's variables so one process
can hold several without collision.
"""

from __future__ import annotations

from billing_platform.broker import BrokerSource
from billing_platform.service_auth import ServiceKey
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SourceCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    issuer: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    broker_user: str = Field(min_length=1, max_length=200)
    secret: SecretStr = Field(min_length=32)
    event_types: frozenset[str] = Field(min_length=1, max_length=1024)

    @field_validator("event_types", mode="before")
    @classmethod
    def json_events(cls, value: object) -> object:
        # Environment JSON arrays must become sets before shared strict validation.
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return frozenset(value)
        return value

    def source(self) -> BrokerSource:
        return BrokerSource(
            ServiceKey(
                self.issuer, "audit", self.event_types, self.secret.get_secret_value().encode()
            ),
            self.broker_user,
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    #: Async SQLAlchemy URL for this service's database, and only this one. The grant
    #: behind it holds INSERT and SELECT on ``audit_event`` and nothing else — the
    #: immutability mechanism is the grant, not application convention (docs/audit.md §4.1).
    database_url: str
    #: Verifies the gateway-signed actor context (``api/auth.py``). The gateway holds the
    #: signing key; the service only verifies, never mints.
    actor_signing_secret: SecretStr
    #: Signs keyset cursors so a tampered or cross-endpoint cursor is a 422, not a window
    #: into another query (``api/listing.py``).
    cursor_signing_secret: SecretStr
    service_name: str = "audit"

    #: Broker — the only ingress for audit events (docs/audit.md §2.1). Optional so the
    #: read API and tests boot without a broker; the consumer process requires it.
    broker_url: str | None = Field(default=None, repr=False)
    source_credentials: dict[str, SourceCredential] = Field(default_factory=dict, max_length=32)
    consumer_exchange: str = "platform.audit"
    consumer_dead_letter_exchange: str = "platform.audit.dead"
    #: Names this consumer in ``processed_message`` (dedupe) and in the chain-writer lock.
    #: A single logical writer per deployment keeps the hash chain cheap (§4.2).
    consumer_name: str = "audit-consumer"
    consumer_queue: str = "audit.events.authenticated.v1"
    #: Deliberately 1: the chain writer is single-threaded so ``sequence`` and
    #: ``prev_hash`` are assigned without a race (docs/audit.md §4.2). Raising this
    #: without a per-tenant sequencer would fork the chain.
    consumer_prefetch: int = Field(default=1, ge=1, le=1)

    #: Retention floor per category, in days (docs/audit.md §6, §7 decision). The
    #: partition-drop job never drops a partition whose whole month is still inside the
    #: longest live category's window. Jurisdiction rules may extend these.
    retention_days_security: int = 7 * 366
    retention_days_money: int = 7 * 366
    retention_days_admin: int = 3 * 366
    retention_days_access: int = 366
    retention_days_system: int = 366

    #: How many monthly partitions to keep provisioned ahead of ``now`` (§6). A missing
    #: future partition means an insert lands in the catch-all ``pmax`` and the monthly
    #: drop can no longer reclaim it — so the create-ahead job runs well in advance.
    partition_months_ahead: int = 3
