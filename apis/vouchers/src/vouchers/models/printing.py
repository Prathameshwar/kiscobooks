"""Revision-bound print work; document facts are frozen before queue admission."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from vouchers.models.core import Record


class VoucherPrintJob(Record, Base):
    __tablename__ = "voucher_print_job"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','RUNNING','READY','FAILED')", name="status"),
        CheckConstraint("attempt >= 0 AND attempt <= 3", name="attempt"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_print_job_voucher",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_print_job_revision",
        ),
        Index("ix_print_job_pending", "tenant_id", "company_id", "status", "id"),
        Index(
            "ix_print_job_request",
            "tenant_id",
            "company_id",
            "request_hash",
            "permission_hash",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    permission_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)


@event.listens_for(Session, "before_flush")
def protect_print_evidence(db: Session, context: object, instances: object) -> None:
    for row in db.dirty:
        if not isinstance(row, VoucherPrintJob):
            continue
        state = inspect(row)
        immutable = {
            "id",
            "tenant_id",
            "company_id",
            "voucher_id",
            "revision_id",
            "permission_hash",
            "request_hash",
            "snapshot",
            "created_at",
            "created_by",
        }
        if any(state.attrs[key].history.has_changes() for key in immutable):
            raise ConflictError("Purchase print source evidence is immutable")
        if (
            "READY" in state.attrs.status.history.deleted
            or "READY" in state.attrs.status.history.unchanged
        ) and db.is_modified(row):
            raise ConflictError("completed Purchase print evidence is immutable")
    if any(isinstance(row, VoucherPrintJob) for row in db.deleted):
        raise ConflictError("Purchase print evidence must be retained")
