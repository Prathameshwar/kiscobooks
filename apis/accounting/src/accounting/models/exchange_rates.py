"""Reviewed, purpose-specific exchange quotes. Approved values are never edited."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from accounting.models.masters import Record


class ExchangeRateQuote(Record):
    __tablename__ = "exchange_rate_quote"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_exchange_rate_quote_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "from_currency",
            "to_currency",
            "purpose",
            "effective_date",
            "approved_slot",
            name="uq_exchange_rate_quote_approved",
        ),
        Index(
            "ix_exchange_rate_quote_asof",
            "tenant_id",
            "company_id",
            "from_currency",
            "to_currency",
            "purpose",
            "effective_date",
            "status",
            "id",
        ),
        CheckConstraint("rate > 0", name=conv("ck_exchange_rate_quote_positive")),
        CheckConstraint("from_currency <> to_currency", name=conv("ck_exchange_rate_quote_pair")),
        CheckConstraint(
            "purpose IN ('ACCOUNTING','GST_GOODS','GST_SERVICES','REVALUATION','SETTLEMENT')",
            name=conv("ck_exchange_rate_quote_purpose"),
        ),
        CheckConstraint(
            "source_kind IN ('MANUAL','CSV','CUSTOMS')", name=conv("ck_exchange_rate_quote_source")
        ),
        CheckConstraint(
            "status IN ('CANDIDATE','APPROVED','WITHDRAWN')",
            name=conv("ck_exchange_rate_quote_status"),
        ),
        CheckConstraint("row_version > 0", name=conv("ck_exchange_rate_quote_version")),
        MARIADB_TABLE_ARGS,
    )
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(27, 12), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="CANDIDATE")
    approved_slot: Mapped[int | None] = mapped_column(
        Computed("CASE WHEN status = 'APPROVED' THEN 1 ELSE NULL END", persisted=True),
        nullable=True,
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    approval_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ExchangeRateUsage(Record):
    """Immutable approved-quote evidence attached to a financial journal line."""

    __tablename__ = "exchange_rate_usage"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_exchange_rate_usage_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "journal_line_id", name="uq_exchange_rate_usage_line"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "journal_line_id"],
            ["journal_line.tenant_id", "journal_line.company_id", "journal_line.id"],
            name="fk_exchange_rate_usage_line",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "quote_id"],
            [
                "exchange_rate_quote.tenant_id",
                "exchange_rate_quote.company_id",
                "exchange_rate_quote.id",
            ],
            name="fk_exchange_rate_usage_quote",
        ),
        Index("ix_exchange_rate_usage_quote", "tenant_id", "company_id", "quote_id", "id"),
        CheckConstraint("rate > 0", name=conv("ck_exchange_rate_usage_positive")),
        MARIADB_TABLE_ARGS,
    )
    journal_line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quote_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(27, 12), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
