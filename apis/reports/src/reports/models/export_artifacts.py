"""Attempt-owned private output; only published evidence is readable as an artifact."""

import datetime as dt
import re
import uuid
from typing import Any, cast

from billing_platform.db.base import Base
from billing_platform.db.history import previous_scalar
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import InstanceState, Mapped, Session, mapped_column

from reports.domain.reporting.jobs import JobState, JobStatus, require_lease
from reports.models.core import Record, scope
from reports.models.framework import ReportJob


class ReportExportArtifact(Record, Base):
    __tablename__ = "report_export_artifact"
    __table_args__ = scope(
        "report_export_artifact",
        {"job_id": "report_job", "run_id": "report_job"},
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "job_id", "attempt"],
            [
                "report_job_attempt.tenant_id",
                "report_job_attempt.company_id",
                "report_job_attempt.job_id",
                "report_job_attempt.attempt",
            ],
            name="fk_report_export_artifact_attempt",
        ),
        UniqueConstraint("storage_key", name="uq_report_export_artifact_storage"),
        Index(
            "ix_report_export_artifact_cleanup",
            "tenant_id",
            "company_id",
            "temporary_cleaned_at",
            "id",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "attempt", name="uq_report_export_artifact_attempt"
        ),
        CheckConstraint(
            "attempt > 0 AND state IN ('STAGING','PUBLISHED')", name="export_artifact_state"
        ),
        CheckConstraint(
            "(state='STAGING' AND content_hash IS NULL "
            "AND byte_count IS NULL AND row_count IS NULL) "
            "OR (state='PUBLISHED' AND content_hash IS NOT NULL "
            "AND byte_count IS NOT NULL AND row_count IS NOT NULL "
            "AND byte_count >= 0 AND row_count >= 0)",
            name="export_artifact_evidence",
        ),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="STAGING")
    storage_key: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(100), nullable=False)
    renderer: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    byte_count: Mapped[int | None] = mapped_column(BigInteger)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    temporary_cleaned_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


@event.listens_for(Session, "before_flush")
def protect_artifacts(db: Session, _context: object, _instances: object) -> None:
    for row in db.new | db.dirty | db.deleted:
        if not isinstance(row, ReportExportArtifact):
            continue
        if row in db.deleted:
            raise ConflictError("report export evidence cannot be deleted")
        cleanup = False
        if row in db.dirty:
            state = cast(InstanceState[Any], inspect(row))
            changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
            if not changed:
                continue
            cleanup = (
                changed <= {"temporary_cleaned_at", "row_version"}
                and row.temporary_cleaned_at is not None
            )
            if cleanup:
                if previous_scalar(db, row, "temporary_cleaned_at") is not None:
                    raise ConflictError("temporary cleanup evidence is immutable")
            elif previous_scalar(db, row, "state") != "STAGING" or row.state != "PUBLISHED":
                raise ConflictError("published export evidence is immutable")
            if not cleanup and changed - {
                "state",
                "content_hash",
                "byte_count",
                "row_count",
                "row_version",
            }:
                raise ConflictError("export identity is immutable")
        elif row.state not in {None, "STAGING"} or row.temporary_cleaned_at is not None:
            raise ConflictError("export artifacts must begin as staging evidence")
        if not re.fullmatch(r"[0-9a-f]{32}", row.storage_key):
            raise ConflictError("private artifact key is invalid")
        if row.state == "PUBLISHED" and (
            not re.fullmatch(r"[0-9a-f]{64}", row.content_hash or "")
            or row.byte_count is None
            or row.byte_count < 0
            or row.row_count is None
            or row.row_count < 0
        ):
            raise ConflictError("published export requires complete byte and row evidence")
        job = db.scalar(
            select(ReportJob)
            .where(
                ReportJob.company_id == row.company_id,
                ReportJob.id == row.job_id,
            )
            .with_for_update()
        )
        if job is None or job.kind != "EXPORT" or job.parent_id != row.run_id:
            raise ConflictError("export artifact does not belong to its completed result")
        if cleanup:
            if job.attempt == row.attempt and job.status in {"QUEUED", "RUNNING"}:
                raise ConflictError("active export temporary files cannot be cleaned")
            continue
        try:
            require_lease(
                JobState(cast(JobStatus, job.status), job.attempt, job.lease_until),
                row.attempt,
                utcnow(),
            )
        except ValueError as exc:
            raise ConflictError("export artifact attempt is fenced") from exc
