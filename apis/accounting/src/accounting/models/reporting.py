"""Owner-retained committed bundles and immutable snapshot pages."""

import uuid
from typing import Any

from billing_platform.db.types import Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import JSON, BigInteger, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class ReportChange(Record):
    __tablename__ = "report_change"
    __table_args__ = constraints(
        "report_change",
        {},
        UniqueConstraint("tenant_id", "company_id", "sequence", name="uq_report_change_sequence"),
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReportChangeFact(Record):
    __tablename__ = "report_change_fact"
    __table_args__ = constraints(
        "report_change_fact",
        {"change_id": "report_change"},
        UniqueConstraint(
            "tenant_id", "company_id", "change_id", "ordinal", name="uq_report_change_fact_ordinal"
        ),
    )
    change_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReportSnapshot(Record):
    __tablename__ = "report_snapshot"
    __table_args__ = constraints("report_snapshot", {})
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReportSnapshotFact(Record):
    __tablename__ = "report_snapshot_fact"
    __table_args__ = constraints(
        "report_snapshot_fact",
        {"snapshot_id": "report_snapshot"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "snapshot_id",
            "ordinal",
            name="uq_report_snapshot_fact_ordinal",
        ),
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


REPORT_MODELS = (ReportChange, ReportChangeFact, ReportSnapshot, ReportSnapshotFact)


@event.listens_for(Session, "before_flush")
def immutable_exports(session: Session, context: object, instances: object) -> None:
    if any(isinstance(row, REPORT_MODELS) and session.is_modified(row) for row in session.dirty):
        raise ConflictError("committed reporting evidence is immutable")
    if any(isinstance(row, REPORT_MODELS) for row in session.deleted):
        raise ConflictError("committed reporting evidence cannot be deleted")
