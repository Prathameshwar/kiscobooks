from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from reporting_contract.authority import AuthoritySource
from reporting_contract.enrollment import EnrollmentSource
from reporting_contract.transport import Owner


class Settings(BaseSettings):
    enrollment_source: EnrollmentSource | None = None
    automatic_sources_enabled: bool = False
    model_config = SettingsConfigDict(
        env_prefix="REPORTS_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    actor_signing_secret: SecretStr = Field(min_length=32)
    artifact_signing_secret: SecretStr = Field(min_length=32)
    database_check_timeout_seconds: float = Field(default=5, gt=0, le=30)
    owners: tuple[Owner, ...] = Field(default=(), max_length=12)
    authority_sources: tuple[AuthoritySource, ...] = Field(default=(), max_length=12)
    framework_enabled: bool = False
    native_queries_enabled: bool = False
    exports_enabled: bool = False
    artifact_root: Path | None = None
    export_max_rows: int = Field(default=1000000, ge=1, le=10000000)
    export_max_bytes: int = Field(default=1073741824, ge=1024, le=10737418240)
    export_timeout_seconds: int = Field(default=600, ge=30, le=7200)
    native_result_limit: int = Field(default=100000, ge=1, le=100000)
    bulk_result_limit: int = Field(default=1000000, ge=1, le=10000000)
    bulk_timeout_seconds: int = Field(default=600, ge=30, le=7200)
    package_max_parts: int = Field(default=100, ge=1, le=1000)
    reference_fact_limit: int = Field(default=20000, ge=1, le=100000)
    source_versions_enabled: bool = False
    source_fact_limit: int = Field(default=100000, ge=1, le=40000000)
    source_parallelism: int = Field(default=4, ge=1, le=8)
    job_broker_url: SecretStr | None = None
    job_queue_namespace: str = Field(default="reports", pattern=r"^[a-z][a-z0-9_.-]{0,59}$")
