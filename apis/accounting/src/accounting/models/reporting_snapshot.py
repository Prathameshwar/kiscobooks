"""Bounded snapshot staging; a completed read-view and its pages are immutable."""

import datetime as dt
import uuid
from typing import Any, cast

from billing_platform.db.history import previous_scalar
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import InstanceState, Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class ReportSnapshotBuild(Record):
    __tablename__ = "report_snapshot_build"
    __table_args__ = constraints(
        "report_snapshot_build",
        {},
        Index("ix_report_snapshot_build_work", "tenant_id", "company_id", "status", "id"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETE','FAILED') AND attempt >= 0 "
            "AND completed_facts >= 0",
            name="report_snapshot_build_valid",
        ),
    )
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_until: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    completed_facts: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class ReportSnapshotBatch(Record):
    __tablename__ = "report_snapshot_batch"
    __table_args__ = constraints(
        "report_snapshot_batch",
        {"build_id": "report_snapshot_build"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "build_id",
            "attempt",
            "first_ordinal",
            name="uq_report_snapshot_batch_ordinal",
        ),
        CheckConstraint(
            "attempt > 0 AND first_ordinal > 0 AND fact_count BETWEEN 1 AND 200",
            name="report_snapshot_batch_valid",
        ),
    )
    build_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    first_ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


SNAPSHOT_MODELS = (ReportSnapshotBuild, ReportSnapshotBatch)


@event.listens_for(Session, "before_flush")
def protect_snapshot(session: Session, context: object, instances: object) -> None:
    from billing_platform.db.types import utcnow
    from billing_platform.idempotency import canonical_json
    from reporting_contract.contract import digest

    for row in session.new:
        if isinstance(row, ReportSnapshotBatch):
            parent = session.scalar(
                select(ReportSnapshotBuild)
                .where(
                    ReportSnapshotBuild.company_id == row.company_id,
                    ReportSnapshotBuild.id == row.build_id,
                )
                .with_for_update()
            )
            if (
                parent is None
                or parent.status != "RUNNING"
                or parent.attempt != row.attempt
                or parent.lease_until is None
                or parent.lease_until <= utcnow()
            ):
                raise ConflictError("snapshot attempt no longer owns its lease")
            if (
                not 1 <= len(row.facts) <= 200
                or len(row.facts) != row.fact_count
                or len(canonical_json(row.facts)) > 900000
                or digest(row.facts) != row.content_hash
            ):
                raise ConflictError("snapshot batch bounds or checksum differ")
    for row in session.dirty | session.deleted:
        if not isinstance(row, ReportSnapshotBuild | ReportSnapshotBatch):
            continue
        if row in session.deleted:
            raise ConflictError("snapshot evidence cannot be deleted")
        if not session.is_modified(row):
            continue
        state = cast(InstanceState[ReportSnapshotBuild | ReportSnapshotBatch], inspect(row))
        changed = {key.key for key in state.attrs if key.history.has_changes()}
        if isinstance(row, ReportSnapshotBatch) or changed & {
            "id",
            "tenant_id",
            "company_id",
            "created_at",
            "created_by",
        }:
            raise ConflictError("snapshot evidence identity is immutable")
        if previous_scalar(session, row, "status") == "COMPLETE":
            raise ConflictError("completed snapshot is immutable")
