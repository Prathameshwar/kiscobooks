"""Append-only count/recount evidence and exactly-once native root claims."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    Index,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.stock import constraints, reference


class StockCountObservation(Record):
    __tablename__ = "stock_count_observation"
    __table_args__ = (
        *constraints("stock_count_observation"),
        UniqueConstraint(
            "tenant_id", "company_id", "root_id", "revision", name="uq_stock_count_revision"
        ),
        Index("ix_stock_count_grain", "tenant_id", "company_id", "item_id", "warehouse_id", "id"),
        CheckConstraint(
            "revision > 0 AND cutoff_generation >= 0 AND book_quantity >= 0",
            name="stock_count_cutoff",
        ),
        CheckConstraint(
            "observed_quantity IS NULL OR observed_quantity >= 0", name="stock_count_observed"
        ),
        CheckConstraint(
            "reviewed_unit_cost IS NULL OR reviewed_unit_cost >= 0", name="stock_count_cost"
        ),
        CheckConstraint(
            "quantity_increment > 0 AND quantity_decimal_places BETWEEN 0 AND 4",
            name="stock_count_grid",
        ),
        MARIADB_TABLE_ARGS,
    )
    root_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    base_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quantity_increment: Mapped[Decimal] = mapped_column(Money, nullable=False)
    quantity_decimal_places: Mapped[int] = mapped_column(nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    stock_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    cutoff_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    cutoff_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    book_quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    observed_quantity: Mapped[Decimal | None] = mapped_column(Money)
    quantity_entry: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    reviewed_unit_cost: Mapped[Decimal | None] = mapped_column(Money)
    cost_review_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_pool_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    reviewed_pool_version: Mapped[int | None] = mapped_column(nullable=True)


class StockCountApplication(Record):
    __tablename__ = "stock_count_application"
    __table_args__ = (
        *constraints("stock_count_application"),
        UniqueConstraint("tenant_id", "company_id", "root_id", name="uq_stock_count_applied_root"),
        reference(
            "observation_id", "stock_count_observation", "fk_stock_count_application_observation"
        ),
        reference("posting_id", "stock_posting", "fk_stock_count_application_posting"),
        MARIADB_TABLE_ARGS,
    )
    root_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    posting_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    difference: Mapped[Decimal] = mapped_column(Money, nullable=False)
    later_quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)


@event.listens_for(Session, "before_flush")
def immutable_count_evidence(db: Session, _context: object, _instances: object) -> None:
    for row in db.deleted | db.dirty:
        if isinstance(row, StockCountObservation | StockCountApplication) and (
            row in db.deleted or db.is_modified(row, include_collections=True)
        ):
            raise ConflictError(
                "native physical count history is immutable; record a new observation"
            )
