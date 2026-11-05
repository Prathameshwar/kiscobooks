"""Company-owned checkout sites and append-only drawer accountability."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from vouchers.models.core import Record


class CounterOutlet(Record, Base):
    __tablename__ = "counter_outlet"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_counter_outlet_scope"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_counter_outlet_code"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class CheckoutCounter(Record, Base):
    __tablename__ = "checkout_counter"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_checkout_counter_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "outlet_id", "code", name="uq_checkout_counter_code"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "outlet_id"],
            ["counter_outlet.tenant_id", "counter_outlet.company_id", "counter_outlet.id"],
            name="fk_checkout_counter_outlet",
        ),
        MARIADB_TABLE_ARGS,
    )
    outlet_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class CounterOperator(Record, Base):
    __tablename__ = "counter_operator"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_counter_operator_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "counter_id", "user_id", name="uq_counter_operator_user"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "counter_id"],
            ["checkout_counter.tenant_id", "checkout_counter.company_id", "checkout_counter.id"],
            name="fk_counter_operator_counter",
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name=conv("ck_counter_operator_status")),
        MARIADB_TABLE_ARGS,
    )
    counter_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class CounterSession(Record, Base):
    __tablename__ = "counter_session"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_counter_session_scope"),
        UniqueConstraint("tenant_id", "company_id", "open_counter_id", name="uq_counter_open"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "counter_id"],
            ["checkout_counter.tenant_id", "checkout_counter.company_id", "checkout_counter.id"],
            name="fk_counter_session_counter",
        ),
        CheckConstraint("status IN ('OPEN','CLOSED')", name="counter_session_status"),
        Index("ix_counter_session_counter", "tenant_id", "company_id", "counter_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    counter_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    open_counter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        Computed("CASE WHEN status = 'OPEN' THEN counter_id ELSE NULL END", persisted=True),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    opened_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    opened_by: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    opening_cash: Mapped[Decimal] = mapped_column(Money, nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    counted_cash: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    variance: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CounterCashEvent(Record, Base):
    __tablename__ = "counter_cash_event"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_counter_cash_event_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "session_id", "event_key", name="uq_counter_cash_event_key"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "session_id"],
            ["counter_session.tenant_id", "counter_session.company_id", "counter_session.id"],
            name="fk_counter_cash_event_session",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_counter_cash_event_voucher",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_counter_cash_event_revision",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "source_revision_id", name="uq_counter_cash_source"
        ),
        CheckConstraint("amount > 0", name="counter_cash_event_amount"),
        CheckConstraint("direction IN ('IN','OUT')", name="counter_cash_event_direction"),
        MARIADB_TABLE_ARGS,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    event_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class VoucherCounterContext(Record, Base):
    __tablename__ = "voucher_counter_context"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_counter_context_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", name="uq_voucher_counter_context_revision"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_counter_context_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "counter_id"],
            ["checkout_counter.tenant_id", "checkout_counter.company_id", "checkout_counter.id"],
            name="fk_voucher_counter_context_counter",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "session_id"],
            ["counter_session.tenant_id", "counter_session.company_id", "counter_session.id"],
            name="fk_voucher_counter_context_session",
        ),
        Index(
            "ix_voucher_counter_list",
            "tenant_id",
            "company_id",
            "counter_id",
            "revision_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    counter_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
