"""Runtime configuration for the `identity` service.

Secrets arrive from the environment or a secret manager, never the repo
(CLAUDE.md §5.9). ``env_prefix`` keeps every service's variables namespaced so one
process can hold several without collision.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from typing import Literal
from urllib.parse import urlsplit

from billing_platform.oidc import OidcConfig
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope as CatalogSourceScope
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CatalogSourceCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    secret: SecretStr = Field(min_length=32)
    scopes: tuple[CatalogSourceScope, ...] = Field(min_length=0, max_length=1000)
    allow_actor_authorization: bool = Field(default=False, strict=True)
    allow_enrolled_companies: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def explicit_scope(self) -> CatalogSourceCredential:
        if not self.scopes and not self.allow_enrolled_companies:
            raise ValueError(
                "source credentials require explicit scopes or enrolled-company authority"
            )
        return self


class OidcSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    issuer: str
    audience: str
    jwks_url: str
    api_scope: str = "billing.api"
    max_token_seconds: int = Field(default=300, ge=60, le=900)

    def configuration(self) -> OidcConfig:
        return OidcConfig(**self.model_dump())


_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


def _plain_url(value: str, *, what: str, path_ok: bool = True) -> str:
    """HTTPS, or HTTP to loopback only; no credentials, query or fragment."""
    parsed = urlsplit(value)
    secure = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in _LOOPBACK)
    if (
        not secure
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or len(value) > 2048
        or (not path_ok and parsed.path not in ("", "/"))
    ):
        raise ValueError(f"{what} must be an explicit HTTPS URL (plain HTTP only for loopback)")
    return value


class LocalClient(BaseModel):
    """A first-party OIDC client of the local provider. Redirects match exactly, never by prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    client_id: str = Field(pattern=r"^[A-Za-z0-9._-]{3,64}$")
    #: SHA-256 (hex) of the client secret. The secret itself is never stored by Identity.
    secret_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    redirect_uris: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("redirect_uris")
    @classmethod
    def exact_redirects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for uri in value:
            _plain_url(uri, what="redirect URI")
        if len(set(value)) != len(value):
            raise ValueError("redirect URIs must be unique")
        return value


class LocalAuthSettings(BaseModel):
    """The local OpenID Connect provider (docs/local-auth.md §2)."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    #: The exact string in every token. The public URL of the OIDC mount.
    issuer: str
    #: Where services fetch keys when the public issuer URL is not reachable from the service.
    jwks_url: str | None = None
    audience: str = Field(min_length=1, max_length=255)
    #: The Auth app origin: the sign-in page and the recovery links live there.
    auth_ui_url: str
    clients: tuple[LocalClient, ...] = Field(min_length=1, max_length=8)
    #: Shared with the Auth app server, which alone may call ``/internal/v1/local-auth/*``.
    bff_secret: SecretStr = Field(min_length=32, repr=False)
    #: Base64 of 32 bytes. Encrypts signing private keys at rest.
    key_encryption_key: SecretStr = Field(repr=False)
    access_token_seconds: int = Field(default=300, ge=60, le=900, strict=True)
    refresh_token_seconds: int = Field(default=43_200, ge=300, le=2_592_000, strict=True)
    #: Longest a sign-in may be renewed by refreshing: after this the password is asked for again.
    session_seconds: int = Field(default=2_592_000, ge=3600, le=7_776_000, strict=True)
    code_seconds: int = Field(default=60, ge=10, le=300, strict=True)
    request_seconds: int = Field(default=600, ge=60, le=3600, strict=True)
    recovery_token_seconds: int = Field(default=600, ge=120, le=3600, strict=True)
    max_failed_attempts: int = Field(default=5, ge=3, le=20, strict=True)
    lockout_seconds: int = Field(default=900, ge=60, le=86_400, strict=True)
    registration_enabled: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def valid(self) -> LocalAuthSettings:
        _plain_url(self.issuer, what="issuer")
        _plain_url(self.auth_ui_url, what="auth_ui_url", path_ok=False)
        if self.jwks_url is not None:
            _plain_url(self.jwks_url, what="jwks_url")
        try:
            key = base64.b64decode(self.key_encryption_key.get_secret_value(), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("key_encryption_key must be base64") from None
        if len(key) != 32:
            raise ValueError("key_encryption_key must decode to 32 bytes")
        ids = [client.client_id for client in self.clients]
        if len(set(ids)) != len(ids):
            raise ValueError("client ids must be unique")
        if self.audience in ids:
            # An ID token's audience is the client id. If that were also the API audience, the ID
            # token — a document for the client, meant to be read and discarded — would be accepted
            # wherever an access token is.
            raise ValueError("audience must differ from every client id")
        return self

    def oidc(self) -> OidcSettings:
        """The verifier settings that match this provider's tokens."""
        return OidcSettings(
            issuer=self.issuer,
            audience=self.audience,
            jwks_url=self.jwks_url or self.issuer.rstrip("/") + "/jwks",
            max_token_seconds=self.access_token_seconds,
        )


class AzureBlobSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_url: str = Field(pattern=r"^https://[a-z0-9]{3,24}\.blob\.core\.windows\.net/?$")
    container: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    managed_identity_client_id: str | None = None

    @field_validator("container")
    @classmethod
    def container_name(cls, value: str) -> str:
        if "--" in value:
            raise ValueError("consecutive hyphens are invalid in container names")
        return value


class ReportEnrollmentCredential(SnapshotCredential):
    requester: Literal["reports", "accounting", "catalog"]


class Settings(BaseSettings):
    report_enrollment_credentials: dict[str, ReportEnrollmentCredential] = Field(
        default_factory=dict, max_length=12
    )
    company_setup_origins: dict[str, str] = Field(default_factory=dict, max_length=4)

    @field_validator("company_setup_origins")
    @classmethod
    def setup_origins(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) - {"catalog", "accounting", "vouchers", "reports"}:
            raise ValueError("unsupported setup owner")
        return {
            key: _plain_url(url, what="setup owner", path_ok=False).rstrip("/")
            for key, url in value.items()
        }

    stock_reservation_request_secret: SecretStr | None = Field(
        default=None, min_length=32, repr=False
    )
    stock_reservation_response_secret: SecretStr | None = Field(
        default=None, min_length=32, repr=False
    )
    reference_sync_credentials: dict[str, SecretStr] = Field(default_factory=dict, max_length=2)

    @field_validator("reference_sync_credentials")
    @classmethod
    def validate_reference_credentials(cls, value: dict[str, SecretStr]) -> dict[str, SecretStr]:
        if set(value) - {"catalog", "accounting"} or any(
            len(secret.get_secret_value().encode()) < 32 for secret in value.values()
        ):
            raise ValueError(
                "reference credentials require supported consumers and 32-byte secrets"
            )
        return value

    report_authority_credentials: dict[str, SnapshotCredential] = Field(
        default_factory=dict, max_length=12
    )
    voucher_snapshot_credentials: dict[str, SnapshotCredential] = Field(
        default_factory=dict, max_length=12
    )

    model_config = SettingsConfigDict(env_prefix="IDENTITY_", extra="ignore")

    #: Async SQLAlchemy URL for this service's database, and only this one — the
    #: grant behind it reaches no other schema (CLAUDE.md §5.3, plan §3 / D0).
    database_url: str
    #: Verifies the gateway-signed actor context (``api/auth.py``). The gateway holds
    #: the matching signing key; Identity also mints short-lived downstream contexts.
    actor_signing_secret: SecretStr
    #: Signs keyset cursors so a tampered or cross-endpoint cursor is a 422, not a
    #: window into another query (``api/listing.py``).
    cursor_signing_secret: SecretStr
    service_name: str = "identity"
    oidc: OidcSettings | None = None
    #: Who owns credentials. `local` is Identity's own OIDC provider (docs/local-auth.md);
    #: `authentik` keeps every Authentik flow. Chosen once per installation.
    auth_provider: Literal["local", "authentik"] = "local"
    local_auth: LocalAuthSettings | None = None
    azure_blob: AzureBlobSettings | None = None
    public_auth_url: str | None = None
    notification_platform_tenant_id: uuid.UUID | None = None
    notification_platform_space_id: uuid.UUID | None = None
    notification_platform_key_id: str = "current"
    notification_platform_encryption_key: SecretStr | None = None
    #: Backs proofs, permission resolution and global reference choice caches
    #: (org-model §5.2). When unset, the service resolves grants live from the database
    #: on every request and step-up is unavailable.
    redis_url: SecretStr | None = None
    #: TTL for a cached grant set. This *is* the revocation bound (CLAUDE.md §5.4): a
    #: role change not caught by eager invalidation takes effect within this window.
    #: Short by design — a stale grant is an authorization decision made on old data.
    authz_cache_ttl_seconds: int = Field(default=30, ge=1, le=300, strict=True)
    #: Global reference choices only. Zero disables caching; database generation
    #: changes invalidate immediately, independently of this retention bound.
    reference_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600, strict=True)
    #: Resolved display-only company/user presentation projection. Zero disables it;
    #: versioned keys make committed source or field-access changes immediate.
    company_display_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600, strict=True)

    @field_validator(
        "reference_cache_ttl_seconds", "company_display_cache_ttl_seconds", mode="before"
    )
    @classmethod
    def cache_ttl(cls, value: object) -> object:
        # Environment settings arrive as strings even when a field is strict.
        if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 4:
            return int(value)
        return value

    platform_operators: dict[str, uuid.UUID] = Field(default_factory=dict, max_length=100)
    authentik_review_url: str | None = Field(default=None, pattern=r"^https://[^/?#]+/?$")
    authentik_review_token: SecretStr | None = Field(default=None, min_length=32)
    authentik_recovery_url: str | None = Field(default=None, pattern=r"^https://[^/?#]+/?$")
    authentik_recovery_token: SecretStr | None = Field(default=None, min_length=32)
    authentik_recovery_email_stage: uuid.UUID | None = None
    authentik_provision_url: str | None = Field(default=None, pattern=r"^https://[^/?#]+/?$")
    authentik_provision_token: SecretStr | None = Field(default=None, min_length=32)
    authentik_ca_file: str | None = None
    setup_key: SecretStr | None = Field(default=None, min_length=32, max_length=128)
    bank_active_key_id: str | None = Field(default=None, max_length=80)
    bank_encryption_keys: dict[str, SecretStr] = Field(default_factory=dict, max_length=8)
    billing_reservation_credentials: dict[str, CatalogSourceCredential] = Field(
        default_factory=dict, max_length=4
    )
    billing_reservation_response_secret: SecretStr | None = Field(default=None, min_length=32)
    accounting_reservation_credentials: dict[str, CatalogSourceCredential] = Field(
        default_factory=dict, max_length=4
    )
    accounting_reservation_response_secret: SecretStr | None = Field(default=None, min_length=32)
    catalog_source_credentials: dict[str, CatalogSourceCredential] = Field(
        default_factory=dict, max_length=4
    )
    catalog_source_response_key_id: str = Field(
        default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$"
    )
    catalog_source_response_secret: SecretStr | None = Field(default=None, min_length=32)
    catalog_source_ttl_seconds: int = Field(default=60, ge=15, le=300, strict=True)

    @field_validator("billing_reservation_credentials")
    @classmethod
    def reservation_scopes_are_static(
        cls, value: dict[str, CatalogSourceCredential]
    ) -> dict[str, CatalogSourceCredential]:
        if any(entry.allow_enrolled_companies for entry in value.values()):
            raise ValueError("billing posting requires explicit company scopes")
        return value

    @model_validator(mode="after")
    def local_tokens_are_verified_by_default(self) -> Settings:
        # The provider that issues the tokens also tells the verifier what to expect, so the two
        # cannot be configured apart. With the local provider its settings are authoritative: a
        # leftover `IDENTITY_OIDC` from an Authentik install would otherwise make every token the
        # provider issues fail verification.
        if self.auth_provider == "local" and self.local_auth is not None:
            self.oidc = self.local_auth.oidc()
        elif self.auth_provider == "local" and self.oidc is not None:
            # An installation upgraded from Authentik that never chose a provider. Starting anyway
            # would verify Authentik's tokens while review, provisioning and recovery quietly switch
            # to the local tables: an empty review queue and 503s with no explanation.
            raise ValueError(
                "IDENTITY_OIDC is set but the sign-in provider is 'local' (the default) and "
                "IDENTITY_LOCAL_AUTH is not configured. Set IDENTITY_AUTH_PROVIDER=authentik "
                "to keep using Authentik, or configure the local provider "
                "(start/win/local-auth.bat)."
            )
        return self


__all__ = [
    "CatalogSourceCredential",
    "CatalogSourceScope",
    "LocalAuthSettings",
    "LocalClient",
    "Settings",
]
