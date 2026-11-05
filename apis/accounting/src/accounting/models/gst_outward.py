"""Append-only, scoped detailed GST outward evidence and exact monetary totals."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import JSON, Date, Index, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class GstOutwardRecord(Record):
    __tablename__ = "gst_outward_record"
    __table_args__ = constraints(
        "gst_outward_record",
        {"original_record_id": "gst_outward_record"},
        Index(
            "ix_gst_outward_period",
            "tenant_id",
            "company_id",
            "registration_id",
            "return_date",
            "id",
        ),
        Index(
            "ix_gst_outward_native",
            "tenant_id",
            "company_id",
            "registration_id",
            "source_entity",
            "source_id",
            "kind",
        ),
    )
    registration_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    return_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    document_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    document_number: Mapped[str] = mapped_column(String(16), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    original_record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    invoice_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    igst: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sgst: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cess: Mapped[Decimal] = mapped_column(Money, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


@event.listens_for(Session, "before_flush")
def immutable(db: Session, context: object, instances: object) -> None:
    if any(
        isinstance(row, GstOutwardRecord) and (row in db.deleted or db.is_modified(row))
        for row in db.dirty | db.deleted
    ):
        raise ConflictError(
            "committed outward GST evidence is immutable; append a linked correction"
        )
