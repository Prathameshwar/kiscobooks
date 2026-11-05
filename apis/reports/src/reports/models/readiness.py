"""Durable source reconciliation health, distinct from immutable report evidence."""

import datetime as dt

from billing_platform.db.base import Base
from billing_platform.db.types import UtcDateTime
from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from reports.models.core import Record, scope


class ReportReadiness(Record, Base):
    __tablename__ = "report_readiness"
    __table_args__ = scope(
        "report_readiness",
        {},
        UniqueConstraint("tenant_id", "company_id", name="uq_report_readiness_company"),
    )
    owner_sequence: Mapped[int | None] = mapped_column(BigInteger)
    checked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    next_attempt_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(60))
