"""Environment-only configuration; encryption is required before beneficiary writes."""

import httpx
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from reporting_contract.catalog_stock import CatalogStockOwner
from reporting_contract.enrollment import EnrollmentSource


class CatalogTaxCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    secret: SecretStr = Field(min_length=32)
    scopes: list[CompanyServiceScope] = Field(min_length=1, max_length=1000)


class Settings(BaseSettings):
    report_enrollment_source: EnrollmentSource | None = None
    voucher_stock_enabled: bool = False
    stock_owner_url: str | None = Field(default=None, max_length=300)
    stock_owner_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    stock_retirement_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    stock_policy_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    stock_execution_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    stock_catalog_url: str | None = Field(default=None, max_length=300)
    stock_identity_url: str | None = Field(default=None, max_length=300)
    stock_identity_request_secret: SecretStr | None = Field(default=None, min_length=32, repr=False)
    stock_identity_response_secret: SecretStr | None = Field(
        default=None, min_length=32, repr=False
    )

    @model_validator(mode="after")
    def stock_identity_connection(self) -> "Settings":
        values = (
            self.stock_identity_url,
            self.stock_identity_request_secret,
            self.stock_identity_response_secret,
        )
        if any(values) and not all(values):
            raise ValueError("stock Identity connection must be supplied together")
        return self

    @field_validator("stock_catalog_url", "stock_owner_url", "stock_identity_url")
    @classmethod
    def catalog_tracking_origin(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None:
            url = httpx.URL(value)
            if (
                not url.host
                or url.userinfo
                or url.query
                or url.fragment
                or (info.field_name != "stock_catalog_url" and url.path not in {"", "/"})
                or (
                    url.scheme != "https"
                    and not (url.scheme == "http" and url.host in {"localhost", "127.0.0.1", "::1"})
                )
            ):
                raise ValueError(
                    "Catalog tracking URL must use HTTPS or local loopback without credentials"
                )
        return value

    voucher_money_enabled: bool = False
    voucher_invoice_enabled: bool = False
    report_credentials: dict[str, SnapshotCredential] = Field(default_factory=dict, max_length=12)
    report_snapshot_enabled: bool = False
    stock_report_catalog: CatalogStockOwner | None = None
    report_snapshot_fact_limit: int = Field(default=100000, ge=1, le=40000000)
    report_snapshot_seconds: int = Field(default=900, ge=10, le=3600)
    report_snapshot_parallelism: int = Field(default=4, ge=1, le=8)
    voucher_execution_credentials: dict[str, SnapshotCredential] = Field(
        default_factory=dict, max_length=12
    )
    voucher_snapshot_credentials: dict[str, SnapshotCredential] = Field(
        default_factory=dict, max_length=12
    )

    model_config = SettingsConfigDict(
        env_prefix="ACCOUNTING_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    actor_signing_secret: SecretStr = Field(min_length=32)
    encryption_key: SecretStr | None = None
    identity_posting_url: str | None = Field(default=None, max_length=300)
    identity_posting_key_id: str | None = Field(default=None, min_length=1, max_length=120)
    identity_posting_secret: SecretStr | None = Field(default=None, min_length=32)
    identity_posting_response_keys: dict[str, SecretStr] = Field(default_factory=dict, max_length=4)
    catalog_tax_credentials: dict[str, CatalogTaxCredential] = Field(
        default_factory=dict, max_length=8
    )
    database_check_timeout_seconds: float = Field(default=5, gt=0, le=30)
    #: State codes that levy UTGST instead of SGST (Union Territories without a legislature),
    #: from reference data; ``IN-CH`` and ``CH`` are equivalent.
    utgst_states: frozenset[str] = Field(default=frozenset(), max_length=40)

    @field_validator("encryption_key")
    @classmethod
    def encryption_format(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(bytes.fromhex(value.get_secret_value())) != 32:
            raise ValueError("encryption key must contain 32 hex-encoded bytes")
        return value

    @model_validator(mode="after")
    def posting_configuration(self) -> "Settings":
        values = (
            self.identity_posting_url,
            self.identity_posting_key_id,
            self.identity_posting_secret,
            self.identity_posting_response_keys,
        )
        if any(values) and not all(values):
            raise ValueError("Identity posting configuration must be supplied together")
        if self.identity_posting_url is not None:
            url = httpx.URL(self.identity_posting_url)
            if (
                url.scheme != "https"
                or not url.host
                or url.path not in {"", "/"}
                or url.query
                or url.fragment
                or url.userinfo
            ):
                raise ValueError("Identity posting URL must be an HTTPS origin without credentials")
        if any(
            len(value.get_secret_value()) < 32
            for value in self.identity_posting_response_keys.values()
        ):
            raise ValueError("Identity response keys must contain at least 32 characters")
        return self
