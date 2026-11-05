"""Environment-only settings; no flag can enable an unimplemented Catalog capability."""

from billing_platform.owner_snapshot import SnapshotCredential
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from reporting_contract.enrollment import EnrollmentSource
from voucher_execution.retirement_transport import RetirementConnection
from voucher_execution.stock_policy_transport import PolicyConnection

from catalog.tasks.identity_source import IdentitySourceSettings


class Settings(BaseSettings):
    simple_creation_origins: dict[str, str] = Field(default_factory=dict, max_length=2)
    report_enrollment_source: EnrollmentSource | None = None
    stock_report_credentials: dict[str, SnapshotCredential] = Field(
        default_factory=dict, max_length=12
    )
    voucher_snapshot_credentials: dict[str, SnapshotCredential] = Field(
        default_factory=dict, max_length=12
    )

    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )

    database_url: str = Field(repr=False)
    identity_source: IdentitySourceSettings | None = None
    actor_signing_secret: SecretStr
    # A separate owner key never grants a company: each call additionally proves
    # the real actor's exact company grant against fresh Identity enrollment.
    stock_owner_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    stock_retirement_accounting: RetirementConnection | None = None
    stock_retirement_vouchers: RetirementConnection | None = None
    stock_policy_accounting: PolicyConnection | None = None
    database_check_timeout_seconds: float = Field(default=5, gt=0, le=30)

    @field_validator("simple_creation_origins")
    @classmethod
    def creation_origins(cls, value: dict[str, str]) -> dict[str, str]:
        from urllib.parse import urlsplit

        for service, origin in value.items():
            parsed = urlsplit(origin)
            if (
                service not in {"accounting", "vouchers"}
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("simple creation requires configured owner origins")
        return {key: origin.rstrip("/") for key, origin in value.items()}

    @field_validator("actor_signing_secret")
    @classmethod
    def secret_has_sufficient_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("actor signing secret requires at least 32 bytes")
        return value
