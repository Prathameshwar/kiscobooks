"""Source-bound credit reservations and separately approved exceptions."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import JSON, CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class CreditOverride(Record):
    __tablename__ = "credit_override"
    __table_args__ = constraints(
        "credit_override",
        {"account_id": "account"},
        CheckConstraint(
            "status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'USED')", name="credit_override_status"
        ),
        CheckConstraint("amount > 0", name="credit_override_amount"),
        Index(
            "ix_credit_override_source",
            "tenant_id",
            "company_id",
            "source_system",
            "source_type",
            "source_id",
            "id",
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CreditReservation(Record):
    __tablename__ = "credit_reservation"
    __table_args__ = constraints(
        "credit_reservation",
        {
            "account_id": "account",
            "party_id": "party",
            "journal_id": "journal",
            "override_id": "credit_override",
        },
        CheckConstraint(
            "status IN ('ACTIVE', 'CONSUMED', 'RELEASED')", name="credit_reservation_status"
        ),
        CheckConstraint("amount > 0 AND base_amount > 0", name="credit_reservation_amount"),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="credit_reservation_role"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_system",
            "source_type",
            "source_id",
            name="uq_credit_reservation_source",
        ),
        Index(
            "ix_credit_reservation_exposure",
            "tenant_id",
            "company_id",
            "party_id",
            "role",
            "status",
            "expires_at",
            "id",
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    override_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


CREDIT_MODELS = (CreditOverride, CreditReservation)
