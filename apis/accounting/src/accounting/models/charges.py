"""Effective-dated charge terms and immutable approved calculation evidence."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class ChargePolicy(Record):
    __tablename__ = "charge_policy"
    __table_args__ = constraints(
        "charge_policy",
        {"account_id": "account", "offset_account_id": "account"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "account_id",
            "currency",
            "valid_from",
            name="uq_charge_policy_effective",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="charge_policy_dates"),
        CheckConstraint(
            "method IN ('FIXED', 'INTEREST') AND compound IN ('SIMPLE', 'DAILY')",
            name="charge_policy_method",
        ),
        CheckConstraint(
            "rate > 0 AND minimum >= 0 AND (cap IS NULL OR cap >= minimum)",
            name="charge_policy_amount",
        ),
        CheckConstraint(
            "day_basis IN (360,365) AND grace_days BETWEEN 0 AND 3650", name="charge_policy_days"
        ),
        Index(
            "ix_charge_policy_asof",
            "tenant_id",
            "company_id",
            "account_id",
            "currency",
            "valid_from",
            "valid_to",
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    offset_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    accrual_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    rate_period: Mapped[str] = mapped_column(String(20), nullable=False)
    compound: Mapped[str] = mapped_column(String(20), nullable=False)
    basis: Mapped[str] = mapped_column(String(20), nullable=False)
    day_basis: Mapped[int] = mapped_column(Integer, nullable=False)
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cap: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    charge_on_charge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tax_treatment: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_reason: Mapped[str] = mapped_column(String(500), nullable=False)


class ChargeAssessment(Record):
    __tablename__ = "charge_assessment"
    __table_args__ = constraints(
        "charge_assessment",
        {"item_id": "open_item", "policy_id": "charge_policy", "journal_id": "journal"},
        UniqueConstraint(
            "tenant_id", "company_id", "journal_id", name="uq_charge_assessment_journal"
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'POSTED', 'WAIVED', 'REVERSED', 'REJECTED')",
            name="charge_assessment_status",
        ),
        CheckConstraint(
            "amount > 0 AND cumulative_amount >= amount AND exchange_rate > 0",
            name="charge_assessment_amount",
        ),
        CheckConstraint("coverage_end_date > coverage_start_date", name="charge_assessment_dates"),
        Index(
            "ix_charge_assessment_coverage",
            "tenant_id",
            "company_id",
            "item_id",
            "coverage_end_date",
            "id",
        ),
        Index(
            "ix_charge_assessment_status", "tenant_id", "company_id", "status", "posting_date", "id"
        ),
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    coverage_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    coverage_end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cumulative_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(19, 8, asdecimal=True), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ChargeTaxSnapshot(Record):
    __tablename__ = "charge_tax_snapshot"
    __table_args__ = constraints(
        "charge_tax_snapshot",
        {"assessment_id": "charge_assessment"},
        UniqueConstraint(
            "tenant_id", "company_id", "assessment_id", name="uq_charge_tax_assessment"
        ),
        UniqueConstraint("tenant_id", "company_id", "provider_id", name="uq_charge_tax_provider"),
        CheckConstraint("net_amount > 0 AND gross_amount >= net_amount", name="charge_tax_amount"),
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str] = mapped_column(String(120), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


CHARGE_MODELS = (ChargePolicy, ChargeAssessment, ChargeTaxSnapshot)
