from __future__ import annotations

import uuid

from billing_platform.service_auth import CompanyServiceScope
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IdentitySource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    secret: SecretStr = Field(min_length=32)
    broker_user: str = Field(min_length=1, max_length=200)


class AccountingSource(IdentitySource):
    scopes: list[CompanyServiceScope] = Field(min_length=1, max_length=1000)


class VoucherSource(IdentitySource):
    scopes: list[CompanyServiceScope] = Field(min_length=1, max_length=1000)


class PlatformSource(IdentitySource):
    owner_tenant_id: uuid.UUID


class OwnershipBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: uuid.UUID
    space_id: uuid.UUID


class CredentialBinding(OwnershipBinding):
    allowed_senders: list[str] = Field(default_factory=list, max_length=1000)
    environment_variable: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,119}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOTIFICATION_", extra="ignore", hide_input_in_errors=True
    )

    platform_sources: dict[str, PlatformSource] = Field(default_factory=dict, max_length=4)
    platform_ingress_keys: dict[str, SecretStr] = Field(default_factory=dict, max_length=4)
    credential_bindings: dict[str, CredentialBinding] = Field(default_factory=dict)
    callback_public_origin: str | None = None
    meta_verification_token_ref: str | None = None
    sns_topic_bindings: dict[str, OwnershipBinding] = Field(default_factory=dict)
    platform_owner_tenant_id: uuid.UUID | None = None
    platform_space_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def platform_ownership(self) -> Settings:
        owner, space = self.platform_owner_tenant_id, self.platform_space_id
        if (owner is None) != (space is None):
            raise ValueError("platform owner and space must be configured together")
        if (
            owner is not None
            and space is not None
            and (not owner.int or not space.int or owner == space)
        ):
            raise ValueError("platform ownership requires distinct non-sentinel identifiers")
        return self

    database_url: str
    actor_signing_secret: SecretStr = Field(min_length=32)
    cursor_signing_secret: SecretStr = Field(min_length=32)
    data_encryption_key: SecretStr = Field(min_length=32)
    data_encryption_key_ref: str = "env:NOTIFICATION_DATA_ENCRYPTION_KEY"
    callback_max_body_bytes: int = 1_048_576
    service_name: str = "notification"

    # Broker — the only send-command ingress (docs/notification.md §2.1). Optional so the
    # API and tests boot without a broker; the consumer process requires it.
    broker_url: str | None = None
    identity_auth_origin: str | None = None
    identity_sources: dict[str, IdentitySource] = Field(default_factory=dict, max_length=4)
    voucher_sources: dict[str, VoucherSource] = Field(default_factory=dict, max_length=12)
    accounting_sources: dict[str, AccountingSource] = Field(default_factory=dict, max_length=12)
    consumer_name: str = "notification-consumer"
    consumer_queue: str = "notification.send"
    consumer_prefetch: int = 16
    dispatch_enabled: bool = False
    dispatch_per_provider_minute: int = Field(default=120, ge=1, le=100000)
    dispatch_per_space_channel_minute: int = Field(default=300, ge=1, le=100000)

    # Maintenance windows (docs/notification.md §6, docs/notification-operations.md).
    content_retention_days: int = Field(default=90, ge=90, le=3650)
    provider_event_retention_days: int = Field(default=90, ge=90, le=3650)
    stuck_sending_seconds: int = 900
