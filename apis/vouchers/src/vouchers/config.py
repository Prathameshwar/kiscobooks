"""Environment-only credentials and bounded service scopes."""

from pathlib import Path
from typing import Literal, Self

from billing_platform.errors import ConflictError
from billing_platform.service_auth import CompanyServiceScope
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vouchers.schemas.owners import Owner, StockExecutionOwner
from vouchers.schemas.printing import PrintLayoutOwner


class SourceCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    issuer: Literal["identity", "catalog", "accounting"]
    operations: frozenset[Literal["vouchers.sources.apply", "vouchers.execution.result"]] = (
        frozenset({"vouchers.sources.apply"})
    )
    secret: SecretStr = Field(min_length=32)
    scopes: list[CompanyServiceScope] = Field(default_factory=list, max_length=1000)
    allow_enrolled_companies: bool = False

    @model_validator(mode="after")
    def require_scope(self) -> Self:
        if not self.scopes and not self.allow_enrolled_companies:
            raise ValueError("source credential requires a company scope")
        if self.allow_enrolled_companies and self.issuer != "catalog":
            raise ValueError("dynamic source delivery is limited to Catalog")
        return self


class PrintRuntime(BaseSettings):
    """Worker configuration deliberately has no interactive actor signing credentials."""

    model_config = SettingsConfigDict(
        env_prefix="VOUCHERS_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    print_file_root: Path | None = None
    print_broker_url: SecretStr | None = Field(default=None, min_length=1, repr=False)
    print_scopes: list[CompanyServiceScope] = Field(default_factory=list, max_length=1000)
    print_browser_executable: Path | None = None
    print_timeout_seconds: int = Field(default=90, ge=15, le=120)
    # The deployment environment of this process. An undeclared environment is production.
    environment: Literal["development", "staging", "production"] = "production"
    # The browser sandbox is ON everywhere. This switch exists only for a developer machine whose
    # sandboxed browser cannot start; it is refused unless `environment` is "development", and it
    # is never read from, or shown by, any request or response.
    print_chromium_sandbox: bool = True

    @field_validator("print_file_root", "print_browser_executable")
    @classmethod
    def absolute_print_location(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("private print and browser locations must be absolute")
        return value

    @model_validator(mode="after")
    def sandbox_off_only_in_development(self) -> Self:
        if not self.print_chromium_sandbox and self.environment != "development":
            raise ValueError(
                "the Chromium sandbox can be disabled only when VOUCHERS_ENVIRONMENT is development"
            )
        return self


def chromium_sandbox(settings: PrintRuntime) -> bool:
    """Whether the renderer's browser runs sandboxed; the one place the answer is decided.

    Settings are mutable after construction, so the local-only rule is enforced again here,
    where the browser is about to start, and not only when the settings were validated.
    """
    # Fail safe: anything other than an explicit `False` keeps the sandbox.
    if getattr(settings, "print_chromium_sandbox", True) is not False:
        return True
    if getattr(settings, "environment", "production") != "development":
        raise ConflictError("the Chromium sandbox cannot be disabled outside development")
    return False


class Settings(PrintRuntime):
    print_layout_owner: PrintLayoutOwner | None = None
    # Private VM volume, outside nginx/Next public roots; unset disables uploads.
    supporting_file_root: Path | None = None

    @field_validator("supporting_file_root")
    @classmethod
    def absolute_private_root(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("private file and browser locations must be absolute")
        return value

    money_execution_enabled: bool = False
    invoice_execution_enabled: bool = False
    stock_execution_enabled: bool = False
    stock_retirement_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    execution_owner: Owner | None = None
    stock_execution_owner: StockExecutionOwner | None = None
    # Signed exact-code master lookup at Accounting for bulk imports.
    master_lookup_owner: Owner | None = None
    model_config = SettingsConfigDict(
        env_prefix="VOUCHERS_", extra="ignore", hide_input_in_errors=True
    )
    actor_signing_secret: SecretStr = Field(min_length=32)
    source_credentials: dict[str, SourceCredential] = Field(default_factory=dict, max_length=12)
    artifact_signing_secret: SecretStr = Field(min_length=32)
    database_check_timeout_seconds: int = Field(default=5, ge=1, le=30)
