"""Additive framework storage. Legacy runs/artifacts retain their original lifecycle."""

import datetime as dt
import uuid
from typing import Any, cast

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.history import previous_scalar
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
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
from reports.models.hierarchy import ReportHierarchyNode


class ReportTenantQuota(IdMixin, TenantMixin, Base):
    """One short lock per tenant for admissions/claims, never for calculation."""

    __tablename__ = "report_tenant_quota"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_report_tenant_quota_tenant"),
        MARIADB_TABLE_ARGS,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ReportJob(Record, Base):
    __tablename__ = "report_job"
    __table_args__ = scope(
        "report_job",
        {"generation_id": "report_generation", "parent_id": "report_job"},
        Index("ix_report_job_schedule", "tenant_id", "status", "lane", "available_at", "id"),
        Index("ix_report_job_parent", "tenant_id", "company_id", "parent_id", "id"),
        Index("ix_report_job_actor", "tenant_id", "company_id", "actor_id", "kind", "id"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETE','FAILED','BLOCKED','CANCELLED')",
            name="report_job_status",
        ),
        CheckConstraint(
            "kind IN ('RUN','EXPORT') AND lane IN ('SHORT','BULK','RENDER')", name="report_job_kind"
        ),
        CheckConstraint(
            "attempt >= 0 AND completed_rows >= 0 AND row_version > 0", name="report_job_bounds"
        ),
        CheckConstraint(
            "(kind='RUN' AND parent_id IS NULL) OR (kind='EXPORT' AND parent_id IS NOT NULL)",
            name="report_job_parent",
        ),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    lane: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="QUEUED")
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    display: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    permission_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    available_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    completed_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(60))


class ReportJobAttempt(Record, Base):
    __tablename__ = "report_job_attempt"
    __table_args__ = scope(
        "report_job_attempt",
        {"job_id": "report_job"},
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "attempt", name="uq_report_job_attempt_number"
        ),
        CheckConstraint("attempt > 0", name="report_job_attempt_positive"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    outcome: Mapped[str | None] = mapped_column(String(20))


class ReportResultBatch(Record, Base):
    __tablename__ = "report_result_batch"
    __table_args__ = scope(
        "report_result_batch",
        {"job_id": "report_job"},
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "job_id", "attempt"],
            [
                "report_job_attempt.tenant_id",
                "report_job_attempt.company_id",
                "report_job_attempt.job_id",
                "report_job_attempt.attempt",
            ],
            name="fk_report_result_batch_attempt",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "job_id",
            "attempt",
            "first_ordinal",
            name="uq_report_result_batch_ordinal",
        ),
        CheckConstraint(
            "attempt > 0 AND first_ordinal > 0 AND row_count BETWEEN 1 AND 200",
            name="report_result_batch_bounds",
        ),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    first_ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


FRAMEWORK_MODELS = (ReportTenantQuota, ReportJob, ReportJobAttempt, ReportResultBatch)


@event.listens_for(Session, "before_flush")
def protect_evidence(db: Session, _context: object, _instances: object) -> None:
    # A bounded flush may insert 200 locators for one batch. Reuse the scoped locks
    # within this flush, while retaining every locator/lease verification below.
    result_jobs: dict[tuple[uuid.UUID, uuid.UUID], ReportJob] = {}
    result_batches: dict[tuple[uuid.UUID, uuid.UUID, int, uuid.UUID], ReportResultBatch] = {}
    for row in db.new:
        if isinstance(row, ReportJob) and row.options is not None:
            from reports.domain.reporting.views import select as select_view

            try:
                select_view(row.definition.get("views", []), row.options.get("view", "default"))
            except ValueError as exc:
                raise ConflictError("retained view is unavailable") from exc
            if row.options.get("execution", "STANDARD") not in {"STANDARD", "BULK"}:
                raise ConflictError("retained execution is unavailable")
        if isinstance(row, ReportJob) and row.origin is not None:
            from pydantic import ValidationError

            from reports.domain.reporting.contracts import fingerprint
            from reports.schemas.framework import DrilldownOrigin

            try:
                origin = DrilldownOrigin.model_validate(row.origin)
            except ValidationError as exc:
                raise ConflictError("invalid drilldown provenance") from exc
            parent = db.scalar(
                select(ReportJob).where(
                    ReportJob.company_id == row.company_id,
                    ReportJob.id == origin.parent_id,
                )
            )
            if (
                row.kind != "RUN"
                or parent is None
                or parent.kind != "RUN"
                or parent.status != "COMPLETE"
                or parent.attempt != origin.parent_attempt
                or parent.generation_id != row.generation_id
                or parent.actor_id != row.actor_id
                or parent.permission_hash != row.permission_hash
                or parent.display != row.display
                or (
                    not (
                        origin.mapping == "result_query"
                        and fingerprint(row.definition) == fingerprint(parent.definition)
                        and (row.options or {}).get("result_query") is not None
                    )
                    and not any(
                        item["key"] == origin.mapping and item["target"] == row.definition["code"]
                        for item in parent.definition.get("drilldowns", ())
                    )
                )
            ):
                raise ConflictError("drilldown parent scope or retained context differs")
        if isinstance(row, ReportJob) and row.kind == "EXPORT":
            parent = db.scalar(
                select(ReportJob).where(
                    ReportJob.company_id == row.company_id,
                    ReportJob.id == row.parent_id,
                )
            )
            if (
                parent is None
                or parent.kind != "RUN"
                or parent.status != "COMPLETE"
                or parent.generation_id != row.generation_id
            ):
                raise ConflictError("export requires a completed result in the same generation")
        if isinstance(row, ReportResultBatch | ReportHierarchyNode):
            import hashlib

            if isinstance(row, ReportResultBatch):
                encoded = canonical_json(row.rows)
                if (
                    len(row.rows) != row.row_count
                    or not 1 <= row.row_count <= 200
                    or len(encoded) > 1024 * 1024
                    or hashlib.sha256(encoded).hexdigest() != row.content_hash
                ):
                    raise ConflictError("invalid bounded result batch")
            scope = (row.company_id, row.job_id)
            job = result_jobs.get(scope)
            if job is None:
                job = db.scalar(
                    select(ReportJob)
                    .where(ReportJob.company_id == row.company_id, ReportJob.id == row.job_id)
                    .with_for_update()
                )
            if job is None:
                raise ConflictError("result job is unavailable")
            result_jobs[scope] = job
            if isinstance(row, ReportHierarchyNode):
                batch_scope = (row.company_id, row.job_id, row.attempt, row.batch_id)
                batch = result_batches.get(batch_scope)
                if batch is None:
                    batch = db.scalar(
                        select(ReportResultBatch).where(
                            ReportResultBatch.company_id == row.company_id,
                            ReportResultBatch.id == row.batch_id,
                            ReportResultBatch.job_id == row.job_id,
                            ReportResultBatch.attempt == row.attempt,
                        )
                    )
                if (
                    batch is None
                    or not batch.first_ordinal
                    <= row.ordinal
                    < batch.first_ordinal + batch.row_count
                ):
                    raise ConflictError("hierarchy locator is outside its result batch")
                result_batches[batch_scope] = batch
                value = batch.rows[row.ordinal - batch.first_ordinal]
                if any(
                    getattr(row, key) != value.get(key)
                    for key in (
                        "node_key",
                        "parent_key",
                        "depth",
                        "period",
                        "is_zero",
                    )
                ):
                    raise ConflictError("hierarchy locator differs from frozen output")
            try:
                require_lease(
                    JobState(cast(JobStatus, job.status), job.attempt, job.lease_until),
                    row.attempt,
                    utcnow(),
                )
            except ValueError as exc:
                raise ConflictError("result attempt is fenced") from exc
    for row in db.dirty | db.deleted:
        if not isinstance(
            row, ReportJob | ReportJobAttempt | ReportResultBatch | ReportHierarchyNode
        ):
            continue
        if row in db.deleted or isinstance(row, ReportResultBatch | ReportHierarchyNode):
            raise ConflictError("framework evidence is immutable")
        state = cast(InstanceState[Any], inspect(row))
        assert state is not None
        changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
        if isinstance(row, ReportJob):
            if "checkpoint" in changed:
                checkpoint = row.checkpoint
                try:
                    require_lease(
                        JobState(cast(JobStatus, row.status), row.attempt, row.lease_until),
                        row.attempt,
                        utcnow(),
                    )
                except ValueError as exc:
                    raise ConflictError("checkpoint attempt is fenced") from exc
                if (
                    row.kind != "RUN"
                    or (row.options or {}).get("execution") != "BULK"
                    or not isinstance(checkpoint, dict)
                    or checkpoint.get("attempt") != row.attempt
                    or checkpoint.get("row_count") != row.completed_rows
                ):
                    raise ConflictError("checkpoint must describe the owned durable result")
            if changed & {
                "generation_id",
                "parent_id",
                "actor_id",
                "kind",
                "lane",
                "definition",
                "parameters",
                "display",
                "permission_hash",
                "request_hash",
                "origin",
                "options",
            }:
                raise ConflictError("framework request identity is immutable")
            previous = previous_scalar(db, row, "status")
            if previous in {"COMPLETE", "BLOCKED", "CANCELLED"} and changed:
                raise ConflictError("framework job is terminal")
        else:
            previous_end = previous_scalar(db, row, "finished_at")
            if changed & {"job_id", "attempt", "started_at"} or (
                previous_end is not None and changed
            ):
                raise ConflictError("attempt evidence is immutable")
