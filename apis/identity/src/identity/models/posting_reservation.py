"""Durable pre-post freeze. Pending reservations never expire into an unsafe release."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column


class PostingReservation(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "posting_reservation"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "operation_id", name="uq_posting_reservation_operation"
        ),
        Index("ix_posting_reservation_pending", "tenant_id", "company_id", "status"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_execution_id",
            name="uq_posting_reservation_stock_execution",
        ),
        CheckConstraint(
            "(authority_kind = 'GENERAL' AND source_execution_id IS NULL "
            "AND source_command_hash IS NULL AND source_action IS NULL) OR "
            "(authority_kind = 'STOCK' AND source_execution_id IS NOT NULL "
            "AND source_command_hash IS NOT NULL AND source_action IS NOT NULL "
            "AND source_action IN ('POST','REVERSE'))",
            name="posting_reservation_authority",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_posting_reservation_company_owner",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    owner_service: Mapped[str] = mapped_column(
        String(20), nullable=False, default="billing", server_default="billing"
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    aborted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    terminal_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    authority_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="GENERAL", server_default="GENERAL"
    )
    source_execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    source_command_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_action: Mapped[str | None] = mapped_column(String(10), nullable=True)


@event.listens_for(Session, "before_flush")
def preserve_posting_authority(db: Session, context: object, instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, PostingReservation):
            if row in db.deleted or any(
                inspect(row).attrs[key].history.has_changes()
                for key in (
                    "authority_kind",
                    "source_execution_id",
                    "source_command_hash",
                    "source_action",
                )
            ):
                raise ConflictError("posting authority evidence is immutable")
