"""Attempt-fenced locators into immutable report output; amounts stay in result batches."""

import uuid

from billing_platform.db.base import Base
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from reports.models.core import Record, scope


class ReportHierarchyNode(Record, Base):
    __tablename__ = "report_hierarchy_node"
    __table_args__ = scope(
        "report_hierarchy_node",
        {"job_id": "report_job", "batch_id": "report_result_batch"},
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "job_id", "attempt"],
            [
                "report_job_attempt.tenant_id",
                "report_job_attempt.company_id",
                "report_job_attempt.job_id",
                "report_job_attempt.attempt",
            ],
            name="fk_report_hierarchy_node_attempt",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "job_id",
            "attempt",
            "period",
            "node_key",
            name="uq_report_hierarchy_node_key",
        ),
        Index(
            "ix_report_hierarchy_node_children",
            "tenant_id",
            "company_id",
            "job_id",
            "attempt",
            "period",
            "parent_key",
            "ordinal",
        ),
        CheckConstraint(
            "attempt > 0 AND ordinal > 0 AND depth >= 0", name="report_hierarchy_node_bounds"
        ),
        CheckConstraint("period IN ('CURRENT','COMPARATIVE')", name="report_hierarchy_node_period"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(12), nullable=False)
    node_key: Mapped[str] = mapped_column(String(48), nullable=False)
    parent_key: Mapped[str] = mapped_column(String(48), nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    is_zero: Mapped[bool] = mapped_column(Boolean, nullable=False)
