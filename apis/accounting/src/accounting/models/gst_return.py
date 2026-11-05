"""Immutable statutory allocations; money columns retain DECIMAL(19,4)."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import BigInteger, Boolean, Date, Numeric, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class GstReturnRecord(Record):
    __tablename__ = "gst_return_record"
    __table_args__ = constraints("gst_return_record", {"original_record_id": "gst_return_record"})
    registration_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    return_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    original_record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(19, 8, asdecimal=True))
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    igst: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sgst: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cess: Mapped[Decimal] = mapped_column(Money, nullable=False)
    place_of_supply: Mapped[str | None] = mapped_column(String(2))
    recipient: Mapped[str | None] = mapped_column(String(20))
    is_advance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    credit_head: Mapped[str | None] = mapped_column(String(4))
    coverage_area: Mapped[str | None] = mapped_column(String(20))
    coverage_status: Mapped[str | None] = mapped_column(String(20))
    covered_sequence: Mapped[int | None] = mapped_column(BigInteger)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)


@event.listens_for(Session, "before_flush")
def immutable(db: Session, context: object, instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, GstReturnRecord) and (row in db.deleted or db.is_modified(row)):
            raise ConflictError(
                "committed GST return allocations are immutable; append a source-linked adjustment"
            )
