"""Immutable account opening evidence captured with a new master."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.types import Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import JSON, CheckConstraint, Date, Index, String, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class MasterOpeningBalance(Record):
    __tablename__ = "master_opening_balance"
    __table_args__ = constraints(
        "master_opening_balance",
        {"account_id": "account"},
        UniqueConstraint("tenant_id", "company_id", "account_id", name="uq_master_opening_account"),
        UniqueConstraint("tenant_id", "company_id", "source_key", name="uq_master_opening_source"),
        Index("ix_master_opening_status", "tenant_id", "company_id", "status", "id"),
        CheckConstraint(
            "status IN ('PENDING', 'WITHDRAWN', 'POSTING', 'POSTED', 'REVERSED')",
            name="master_opening_status",
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    opening_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    entry: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


@event.listens_for(Session, "before_flush")
def immutable_master_opening(session: Session, flush_context: object, instances: object) -> None:
    for row in session.deleted:
        if isinstance(row, MasterOpeningBalance):
            raise ConflictError("held master openings cannot be deleted; withdraw them")
    for row in session.dirty:
        if isinstance(row, MasterOpeningBalance):
            state = inspect(row)
            if any(
                state.attrs[key].history.has_changes()
                for key in (
                    "account_id",
                    "source_key",
                    "opening_date",
                    "entry",
                    "tenant_id",
                    "company_id",
                )
            ):
                raise ConflictError("held master openings are immutable; withdraw them")
            history = state.attrs.status.history
            if history.has_changes() and history.deleted:
                allowed = {"PENDING": {"WITHDRAWN"}, "POSTING": {"POSTED"}, "POSTED": {"REVERSED"}}
                if row.status not in allowed.get(history.deleted[0], set()):
                    raise ConflictError("master opening status cannot be restored or changed")
