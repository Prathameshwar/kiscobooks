"""Durable company-owned import jobs; payloads never appear in ordinary lists."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.pricing import PricingRow
from catalog.models.tax import reference, scope


def job_reference(name: str, field: str, target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", "job_id", field],
        [f"{target}.tenant_id", f"{target}.company_id", f"{target}.job_id", f"{target}.id"],
        name=f"fk_{name}_{field}",
    )


class BulkJob(PricingRow):
    __tablename__ = "bulk_job"
    __table_args__ = (
        *scope("bulk_job"),
        CheckConstraint("kind IN ('IMPORT','UPDATE')", name="kind"),
        CheckConstraint("mode IN ('CREATE_ONLY','UPDATE_ONLY','UPSERT')", name="mode"),
        CheckConstraint("atomicity IN ('CHANGE_SET','ATOMIC')", name="atomicity"),
        CheckConstraint("on_error IN ('STOP','CONTINUE_INDEPENDENT')", name="on_error"),
        CheckConstraint(
            "state IN ('STAGED','VALIDATING','READY','QUEUED','RUNNING',"
            "'SUCCEEDED','PARTIAL','FAILED','CANCELLED')",
            name="state",
        ),
        CheckConstraint("revision >= 1 AND record_count BETWEEN 1 AND 2000", name="bounds"),
        CheckConstraint(
            "completed_count >= 0 AND completed_count <= record_count", name="completed"
        ),
        CheckConstraint("invalid_count >= 0 AND invalid_count <= record_count", name="invalid"),
        Index("ix_bulk_job_actor", "tenant_id", "company_id", "actor_user_id", "id"),
        Index("ix_bulk_job_work", "tenant_id", "company_id", "state", "id"),
        MARIADB_TABLE_ARGS,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    atomicity: Mapped[str] = mapped_column(String(12), nullable=False)
    on_error: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="STAGED")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    selection_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    identity_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_keys: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class BulkChangeSet(PricingRow):
    __tablename__ = "bulk_change_set"
    __table_args__ = (
        *scope("bulk_change_set"),
        reference("bulk_change_set", "job_id", "bulk_job"),
        UniqueConstraint("tenant_id", "company_id", "job_id", "id", name="uq_bulk_change_set_job"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "logical_key", name="uq_bulk_change_set_key"
        ),
        CheckConstraint("ordinal >= 1 AND record_count BETWEEN 1 AND 100", name="bounds"),
        CheckConstraint(
            "state IN ('STAGED','VALID','INVALID','BLOCKED','APPLIED','FAILED','EXCLUDED')",
            name="state",
        ),
        Index("ix_bulk_change_set_order", "tenant_id", "company_id", "job_id", "ordinal", "id"),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="STAGED")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class BulkJobRecord(PricingRow):
    __tablename__ = "bulk_job_record"
    __table_args__ = (
        *scope("bulk_job_record"),
        reference("bulk_job_record", "job_id", "bulk_job"),
        UniqueConstraint("tenant_id", "company_id", "job_id", "id", name="uq_bulk_job_record_job"),
        job_reference("bulk_job_record", "change_set_id", "bulk_change_set"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "logical_key", name="uq_bulk_job_record_key"
        ),
        CheckConstraint("ordinal >= 1 AND source_row >= 1", name="bounds"),
        CheckConstraint(
            "expected_version IS NULL OR expected_version >= 1", name="expected_version"
        ),
        CheckConstraint(
            "state IN ('STAGED','VALID','INVALID','BLOCKED','APPLIED','FAILED','EXCLUDED')",
            name="state",
        ),
        Index("ix_bulk_job_record_order", "tenant_id", "company_id", "job_id", "ordinal", "id"),
        Index(
            "ix_bulk_job_record_set", "tenant_id", "company_id", "change_set_id", "ordinal", "id"
        ),
        Index(
            "ix_bulk_job_record_target",
            "tenant_id",
            "company_id",
            "job_id",
            "resource",
            "target_key",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    change_set_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    resource: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    target_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_sheet: Mapped[str] = mapped_column(String(100), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="STAGED")
    normalized_input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    prepared_input: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_pins: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class BulkChangeSetEffect(PricingRow):
    __tablename__ = "bulk_change_set_effect"
    __table_args__ = (
        *scope("bulk_change_set_effect"),
        reference("bulk_change_set_effect", "job_id", "bulk_job"),
        job_reference("bulk_change_set_effect", "change_set_id", "bulk_change_set"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "logical_key", name="uq_bulk_change_set_effect_key"
        ),
        CheckConstraint("accepted_revision >= 1", name="revision"),
        Index("ix_bulk_change_set_effect_job", "tenant_id", "company_id", "job_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    change_set_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_pins: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class BulkJobDependency(PricingRow):
    __tablename__ = "bulk_job_dependency"
    __table_args__ = (
        *scope("bulk_job_dependency"),
        reference("bulk_job_dependency", "job_id", "bulk_job"),
        job_reference("bulk_job_dependency", "parent_record_id", "bulk_job_record"),
        job_reference("bulk_job_dependency", "child_record_id", "bulk_job_record"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "job_id",
            "parent_record_id",
            "child_record_id",
            name="uq_bulk_job_dependency_edge",
        ),
        CheckConstraint("parent_record_id <> child_record_id", name="self_edge"),
        Index(
            "ix_bulk_job_dependency_child",
            "tenant_id",
            "company_id",
            "job_id",
            "child_record_id",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    parent_record_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    child_record_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class BulkImportArtifact(PricingRow):
    __tablename__ = "bulk_import_artifact"
    __table_args__ = (
        *scope("bulk_import_artifact"),
        reference("bulk_import_artifact", "job_id", "bulk_job"),
        CheckConstraint("byte_count BETWEEN 0 AND 8388608", name="bounds"),
        Index("ix_bulk_import_artifact_expiry", "tenant_id", "company_id", "expires_at", "id"),
        Index("ix_bulk_import_artifact_job", "tenant_id", "company_id", "job_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    content: Mapped[bytes] = mapped_column(
        LargeBinary().with_variant(MEDIUMBLOB(), "mysql", "mariadb"), nullable=False, deferred=True
    )


BULK_MODELS = (
    BulkJob,
    BulkChangeSet,
    BulkJobRecord,
    BulkChangeSetEffect,
    BulkJobDependency,
    BulkImportArtifact,
)
