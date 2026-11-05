"""Reusable service-local import storage; no domain model references."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
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

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7


class ImportRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


def scope(name: str) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        Index(f"ix_{name}_page", "tenant_id", "company_id", "id"),
    )


def reference(name: str, field: str, target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", field],
        [f"{target}.tenant_id", f"{target}.company_id", f"{target}.id"],
        name=f"fk_{name}_{field}",
    )


class ImportTemplateSnapshot(ImportRow):
    __tablename__ = "import_template_snapshot"
    __table_args__ = (
        *scope(__tablename__),
        Index("ix_import_template_expiry", "tenant_id", "company_id", "expires_at", "id"),
        MARIADB_TABLE_ARGS,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition: Mapped[str] = mapped_column(String(40), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class ImportJob(ImportRow):
    __tablename__ = "import_job"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "template_id", "import_template_snapshot"),
        Index("ix_import_job_actor", "tenant_id", "company_id", "actor_user_id", "id"),
        Index("ix_import_job_expiry", "tenant_id", "company_id", "expires_at", "id"),
        CheckConstraint(
            "revision >= 1 AND row_version >= 1 AND record_count BETWEEN 1 AND 200",
            name="import_job_bounds",
        ),
        CheckConstraint(
            "state IN ('STAGED','READY','INVALID','SUCCEEDED',"
            "'PARTIAL','FAILED','CANCELLED','EXPIRED','VALIDATING','IMPORTING')",
            name="import_job_state",
        ),
        MARIADB_TABLE_ARGS,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="STAGED")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class ImportJobRevision(ImportRow):
    __tablename__ = "import_job_revision"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "job_id", "import_job"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "revision", name="uq_import_revision_number"
        ),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    batch: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)


class ImportChangeSet(ImportRow):
    __tablename__ = "import_change_set"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "revision_id", "import_job_revision"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "logical_key", name="uq_import_set_key"
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class ImportJobRecord(ImportRow):
    __tablename__ = "import_job_record"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "change_set_id", "import_change_set"),
        UniqueConstraint(
            "tenant_id", "company_id", "change_set_id", "logical_key", name="uq_import_record_key"
        ),
        MARIADB_TABLE_ARGS,
    )
    change_set_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file: Mapped[str] = mapped_column(String(120), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(100), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    resource: Mapped[str] = mapped_column(String(80), nullable=False)


class ImportJobDependency(ImportRow):
    __tablename__ = "import_job_dependency"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "parent_id", "import_job_record"),
        reference(__tablename__, "child_id", "import_job_record"),
        CheckConstraint("parent_id <> child_id", name="import_dependency_self"),
        UniqueConstraint(
            "tenant_id", "company_id", "parent_id", "child_id", name="uq_import_dependency_edge"
        ),
        MARIADB_TABLE_ARGS,
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class ImportJobAttempt(ImportRow):
    __tablename__ = "import_job_attempt"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "revision_id", "import_job_revision"),
        CheckConstraint("phase IN ('VALIDATE','IMPORT')", name="import_attempt_phase"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    phase: Mapped[str] = mapped_column(String(8), nullable=False)
    outcome: Mapped[str] = mapped_column(String(12), nullable=False)
    finished_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class ImportChangeSetEffect(ImportRow):
    __tablename__ = "import_change_set_effect"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "job_id", "import_job"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "logical_key", name="uq_import_effect_key"
        ),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ImportRecordResult(ImportRow):
    __tablename__ = "import_record_result"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "attempt_id", "import_job_attempt"),
        reference(__tablename__, "record_id", "import_job_record"),
        UniqueConstraint(
            "tenant_id", "company_id", "attempt_id", "record_id", name="uq_import_result_record"
        ),
        MARIADB_TABLE_ARGS,
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    business_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ImportRecordIssue(ImportRow):
    __tablename__ = "import_record_issue"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "result_id", "import_record_result"),
        MARIADB_TABLE_ARGS,
    )
    result_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    field: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(250), nullable=False)


class ImportArtifact(ImportRow):
    __tablename__ = "import_artifact"
    __table_args__ = (
        *scope(__tablename__),
        reference(__tablename__, "revision_id", "import_job_revision"),
        CheckConstraint("byte_count BETWEEN 0 AND 8388608", name="import_artifact_bounds"),
        Index("ix_import_artifact_expiry", "tenant_id", "company_id", "expires_at", "id"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    format: Mapped[str] = mapped_column(String(5), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    content: Mapped[bytes | None] = mapped_column(
        LargeBinary().with_variant(MEDIUMBLOB(), "mysql", "mariadb"), nullable=True, deferred=True
    )


IMPORT_MODELS = (
    ImportTemplateSnapshot,
    ImportJob,
    ImportJobRevision,
    ImportChangeSet,
    ImportJobRecord,
    ImportJobDependency,
    ImportJobAttempt,
    ImportChangeSetEffect,
    ImportRecordResult,
    ImportRecordIssue,
    ImportArtifact,
)
