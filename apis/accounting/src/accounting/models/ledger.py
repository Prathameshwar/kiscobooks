"""Immutable posted journals and fiscal-year document numbering."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounting.models.masters import Record


class DocumentSequence(Record):
    __tablename__ = "document_sequence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_document_sequence_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "fiscal_year_id",
            "series_key",
            name="uq_document_sequence_series",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "fiscal_year_id"],
            ["fiscal_year.tenant_id", "fiscal_year.company_id", "fiscal_year.id"],
            name="fk_document_sequence_year",
        ),
        CheckConstraint(
            "next_value >= 1 AND next_value <= 999999999", name="document_sequence_next"
        ),
        CheckConstraint("row_version > 0", name="document_sequence_version"),
        MARIADB_TABLE_ARGS,
    )
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    series_key: Mapped[str] = mapped_column(String(30), nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class Journal(Record):
    __tablename__ = "journal"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_journal_scope"),
        UniqueConstraint("tenant_id", "company_id", "number", name="uq_journal_number"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_system",
            "source_type",
            "source_id",
            name="uq_journal_source",
        ),
        UniqueConstraint("tenant_id", "company_id", "live_reversal_id", name="uq_journal_reversal"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "fiscal_period_id"],
            ["fiscal_period.tenant_id", "fiscal_period.company_id", "fiscal_period.id"],
            name="fk_journal_period",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "reversal_of_id"],
            ["journal.tenant_id", "journal.company_id", "journal.id"],
            name="fk_journal_reversal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "authorization_journal_id"],
            ["journal.tenant_id", "journal.company_id", "journal.id"],
            name="fk_journal_authorization",
        ),
        CheckConstraint("row_version > 0", name="journal_version"),
        CheckConstraint("status IN ('DRAFT', 'PREPARED', 'POSTED', 'VOID')", name="journal_status"),
        CheckConstraint(
            "kind IN ('MANUAL', 'OPENING', 'INVOICE', 'BILL', 'RECEIPT', 'PAYMENT', "
            "'CREDIT_NOTE', 'CHARGE', 'REVERSAL', 'REALIZED_FX', 'VOUCHER', 'TAX_ACTION')",
            name="journal_kind",
        ),
        CheckConstraint("total_debit = total_credit AND total_debit > 0", name="journal_balanced"),
        CheckConstraint(
            "(status <> 'POSTED') OR (number IS NOT NULL AND fiscal_period_id IS NOT NULL "
            "AND posted_at IS NOT NULL AND reservation_id IS NOT NULL)",
            name="journal_posted",
        ),
        CheckConstraint(
            "(status NOT IN ('PREPARED', 'POSTED')) OR (prepared_by IS NOT NULL AND "
            "prepared_at IS NOT NULL AND prepared_version IS NOT NULL)",
            name="journal_prepared",
        ),
        Index("ix_journal_page", "tenant_id", "company_id", "id"),
        Index("ix_journal_date", "tenant_id", "company_id", "posting_date", "id"),
        Index("ix_journal_status_date", "tenant_id", "company_id", "status", "posting_date", "id"),
        Index("ix_journal_period", "tenant_id", "company_id", "fiscal_period_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    document_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_debit: Mapped[Decimal] = mapped_column(Money, nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(Money, nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fiscal_period_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    authorization_journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    live_reversal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        Computed("CASE WHEN status = 'VOID' THEN NULL ELSE reversal_of_id END", persisted=True),
        nullable=True,
    )
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    prepared_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    prepared_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    posted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class JournalLine(Record):
    __tablename__ = "journal_line"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_journal_line_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "journal_id", "sequence", name="uq_journal_line_sequence"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "journal_id"],
            ["journal.tenant_id", "journal.company_id", "journal.id"],
            name="fk_journal_line_journal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_journal_line_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_journal_line_party",
        ),
        CheckConstraint("row_version > 0", name="journal_line_version"),
        CheckConstraint("sequence BETWEEN 1 AND 200", name="journal_line_sequence"),
        CheckConstraint("side IN ('DEBIT', 'CREDIT')", name="journal_line_side"),
        CheckConstraint(
            "base_amount > 0 AND exchange_rate > 0 AND "
            "((component = 'PRINCIPAL' AND amount > 0) OR "
            "(component = 'FX' AND amount = 0 AND party_id IS NOT NULL))",
            name="journal_line_amount",
        ),
        CheckConstraint(
            "(party_id IS NULL AND role IS NULL) OR (party_id IS NOT NULL AND role IN "
            "('CUSTOMER', 'SUPPLIER'))",
            name="journal_line_party",
        ),
        Index("ix_journal_line_account", "tenant_id", "company_id", "account_id", "journal_id"),
        Index("ix_journal_line_party", "tenant_id", "company_id", "party_id", "role", "journal_id"),
        MARIADB_TABLE_ARGS,
    )
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PRINCIPAL", server_default="PRINCIPAL"
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(19, 8, asdecimal=True), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


LEDGER_MODELS = (DocumentSequence, Journal, JournalLine)
