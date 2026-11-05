import datetime as dt
import uuid

from billing_platform.db.base import Base
from billing_platform.db.types import Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import Date, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from reports.models.core import Record, scope


class GstReturnReview(Record, Base):
    __tablename__ = "gst_return_review"
    __table_args__ = scope(
        "gst_return_review",
        {"job_id": "report_job"},
        UniqueConstraint("tenant_id", "company_id", "job_id", "state", name="uq_gst_review_state"),
        UniqueConstraint("tenant_id", "company_id", "filed_period_key", name="uq_gst_filed_period"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filed_date: Mapped[dt.date | None] = mapped_column(Date)
    filed_period_key: Mapped[str | None] = mapped_column(String(50))


@event.listens_for(Session, "before_flush")
def immutable(db: Session, context: object, instances: object) -> None:
    if any(
        isinstance(row, GstReturnReview) and (row in db.deleted or db.is_modified(row))
        for row in db.dirty | db.deleted
    ):
        raise ConflictError("GST review and external filing evidence is immutable")
