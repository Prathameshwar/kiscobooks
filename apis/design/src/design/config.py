"""Environment-only credentials and bounded service scopes for the Design service.

Secrets arrive from the environment or a secret manager, never the repo
(CLAUDE.md §5.9). There are deliberately **no defaults** for the database URL or the
signing secrets: a default signing secret is a forged actor context waiting to happen,
and a default database URL is a credential in the repository. Both fail the boot.
"""

from pathlib import Path

from billing_platform.service_auth import CompanyServiceScope
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PrintSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    secret: SecretStr = Field(min_length=32, repr=False)
    scopes: list[CompanyServiceScope] = Field(min_length=1, max_length=1000)


class Settings(BaseSettings):
    """Runtime configuration for the Invoice Designer service."""

    model_config = SettingsConfigDict(
        env_prefix="DESIGN_", extra="ignore", hide_input_in_errors=True
    )

    #: Async SQLAlchemy URL for this service's database, and only this one.
    database_url: str = Field(repr=False)
    #: Verifies the gateway-signed actor context (``api/auth.py``). The gateway holds the
    #: signing key; this service only verifies, never mints.
    actor_signing_secret: SecretStr
    #: Signs keyset cursors. Separate from the actor key: cursors are minted here, and a
    #: service that mints with the key it verifies gateway contexts with could be induced
    #: into signing one.
    cursor_signing_secret: SecretStr
    database_check_timeout_seconds: int = Field(default=5, ge=1, le=30)
    print_source: PrintSource | None = None
    #: Body ceiling for ordinary writes, and the wider one for a canvas version — a
    #: layout tree is the largest legitimate *structural* request here.
    max_body_bytes: int = Field(default=1_048_576, ge=1024, le=52_428_800)
    max_canvas_body_bytes: int = Field(default=5_242_880, ge=1024, le=52_428_800)
    #: An asset upload's own ceiling (plan P4, 2026-11-03): base64 inflates bytes by a
    #: third, so this service's own 5 MiB asset limit
    #: (``schemas/assets.py::MAXIMUM_IMAGE_BYTES``) needs close to 7 MiB of request body
    #: to ever arrive, independent of how large a layout tree may legitimately be.
    max_asset_body_bytes: int = Field(default=7_340_032, ge=1024, le=52_428_800)
    #: Object-store prefix every key this service derives sits under — ``/assets/`` for
    #: brand files, ``/renders/`` for printed artifacts. Clients never supply a storage
    #: path (docs/invoice-design.md §6.3).
    object_storage_prefix: str = Field(default="design", min_length=1, max_length=200)
    object_storage_backend: str = Field(default="S3", min_length=1, max_length=32)
    #: Private VM volume, outside nginx/Next public roots; unset disables asset uploads
    #: and downloads (designer plan P4/D3, 2026-11-03 — the same adapter Purchase PDFs
    #: use, docs/invoice-design.md §9.2).
    asset_storage_root: Path | None = None

    @field_validator("asset_storage_root")
    @classmethod
    def absolute_private_root(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("private asset storage location must be absolute")
        return value

    #: Per-actor write ceiling inside this process, in requests per window. nginx limits
    #: the same paths; this is the in-app half of CLAUDE.md §5.13.
    write_rate_limit: int = Field(default=240, ge=1, le=10_000)

    @field_validator("actor_signing_secret", "cursor_signing_secret")
    @classmethod
    def signing_secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("signing secrets must contain at least 32 characters")
        return value

    @field_validator("object_storage_prefix")
    @classmethod
    def bounded_prefix(cls, value: str) -> str:
        cleaned = value.strip("/")
        simple = cleaned.replace("/", "").replace("-", "").isalnum()
        if not cleaned or ".." in cleaned or not simple:
            raise ValueError("object storage prefix must be a simple object-store path")
        return cleaned
