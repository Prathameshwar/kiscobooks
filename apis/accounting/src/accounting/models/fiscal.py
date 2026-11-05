"""Accounting-owned calendar and authoritative company configuration snapshot."""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounting.models.masters import Record


class FinancialSetup(Record):
    __tablename__ = "financial_setup"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_financial_setup_scope"),
        UniqueConstraint("tenant_id", "company_id", name="uq_financial_setup_company"),
        CheckConstraint("row_version > 0", name="financial_setup_version"),
        CheckConstraint("amount_precision BETWEEN 0 AND 4", name="financial_setup_precision"),
        CheckConstraint(
            "fiscal_year_start_month BETWEEN 1 AND 12 AND fiscal_year_start_day BETWEEN 1 AND 31",
            name="financial_setup_calendar",
        ),
        CheckConstraint(
            "rounding_mode IN ('half_up', 'half_even', 'down')", name="financial_setup_rounding"
        ),
        Index("ix_financial_setup_page", "tenant_id", "company_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    books_begin_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_year_start_day: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_precision: Mapped[int] = mapped_column(Integer, nullable=False)
    rounding_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_posted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class FiscalYear(Record):
    __tablename__ = "fiscal_year"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_fiscal_year_scope"),
        UniqueConstraint("tenant_id", "company_id", "start_date", name="uq_fiscal_year_start"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_fiscal_year_code"),
        CheckConstraint("row_version > 0", name="fiscal_year_version"),
        CheckConstraint("end_date >= start_date", name="fiscal_year_dates"),
        Index("ix_fiscal_year_page", "tenant_id", "company_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)


class FiscalPeriod(Record):
    __tablename__ = "fiscal_period"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_fiscal_period_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "fiscal_year_id",
            "sequence",
            name="uq_fiscal_period_sequence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "fiscal_year_id"],
            ["fiscal_year.tenant_id", "fiscal_year.company_id", "fiscal_year.id"],
            name="fk_fiscal_period_year",
        ),
        CheckConstraint("row_version > 0", name="fiscal_period_version"),
        CheckConstraint("sequence BETWEEN 1 AND 12", name="fiscal_period_sequence"),
        CheckConstraint("end_date >= start_date", name="fiscal_period_dates"),
        CheckConstraint(
            "status IN ('FUTURE', 'OPEN', 'SOFT_CLOSED', 'CLOSED', 'LOCKED')",
            name="fiscal_period_status",
        ),
        Index("ix_fiscal_period_page", "tenant_id", "company_id", "id"),
        Index("ix_fiscal_period_date", "tenant_id", "company_id", "start_date", "end_date"),
        MARIADB_TABLE_ARGS,
    )
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="FUTURE")


class FiscalTransition(Record):
    __tablename__ = "fiscal_status_transition"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_fiscal_transition_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "period_id"],
            ["fiscal_period.tenant_id", "fiscal_period.company_id", "fiscal_period.id"],
            name="fk_fiscal_transition_period",
        ),
        CheckConstraint("row_version > 0", name="fiscal_transition_version"),
        CheckConstraint("from_status <> to_status", name="fiscal_transition_changed"),
        Index("ix_fiscal_transition_period", "tenant_id", "company_id", "period_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    period_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


FISCAL_MODELS = (FinancialSetup, FiscalYear, FiscalPeriod, FiscalTransition)
