"""Opening and subledger facts; monetary facts are reversed, never overwritten."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
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


def constraints(name: str, references: dict[str, str], *extra: Any) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        Index(f"ix_{name}_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name=f"{name}_version"),
        *(
            ForeignKeyConstraint(
                ["tenant_id", "company_id", field],
                [f"{target}.tenant_id", f"{target}.company_id", f"{target}.id"],
                name=f"fk_{name}_{field}",
            )
            for field, target in references.items()
        ),
        *extra,
        MARIADB_TABLE_ARGS,
    )


class OpeningBatch(Record):
    __tablename__ = "opening_batch"
    __table_args__ = constraints(
        "opening_batch",
        {"journal_id": "journal", "replacement_of_id": "opening_batch"},
        UniqueConstraint("tenant_id", "company_id", "journal_id", name="uq_opening_batch_journal"),
        CheckConstraint(
            "status IN ('DRAFT', 'FINALIZED', 'REVERSED', 'VOID')", name="opening_batch_status"
        ),
        Index("ix_opening_batch_status", "tenant_id", "company_id", "status", "id"),
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    replacement_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    finalized_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SourceDocument(Record):
    __tablename__ = "source_document"
    __table_args__ = constraints(
        "source_document",
        {"journal_id": "journal", "account_id": "account", "party_id": "party"},
        UniqueConstraint(
            "tenant_id", "company_id", "journal_id", name="uq_source_document_journal"
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'POSTED', 'REVERSED', 'VOID')", name="source_document_status"
        ),
        CheckConstraint("direction IN ('DEBT', 'CREDIT')", name="source_document_direction"),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="source_document_role"),
        CheckConstraint("amount > 0", name="source_document_amount"),
        Index("ix_source_document_party", "tenant_id", "company_id", "party_id", "role", "id"),
    )
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class OpenItem(Record):
    __tablename__ = "open_item"
    __table_args__ = constraints(
        "open_item",
        {
            "journal_line_id": "journal_line",
            "account_id": "account",
            "party_id": "party",
            "reversal_journal_id": "journal",
        },
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "journal_line_id",
            "sequence",
            name="uq_open_item_line_sequence",
        ),
        CheckConstraint("direction IN ('DEBT', 'CREDIT')", name="open_item_direction"),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="open_item_role"),
        CheckConstraint("amount > 0 AND base_amount > 0 AND sequence > 0", name="open_item_amount"),
        CheckConstraint(
            "(reversal_journal_id IS NULL AND reversal_date IS NULL) OR "
            "(reversal_journal_id IS NOT NULL AND reversal_date IS NOT NULL)",
            name="open_item_reversal",
        ),
        Index(
            "ix_open_item_exposure",
            "tenant_id",
            "company_id",
            "party_id",
            "role",
            "currency",
            "posting_date",
            "id",
        ),
        Index(
            "ix_open_item_account", "tenant_id", "company_id", "account_id", "posting_date", "id"
        ),
        Index("ix_open_item_due", "tenant_id", "company_id", "due_date", "id"),
    )
    journal_line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    document_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    terms: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reversal_journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reversal_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class Allocation(Record):
    __tablename__ = "allocation"
    __table_args__ = constraints(
        "allocation",
        {
            "debt_item_id": "open_item",
            "credit_item_id": "open_item",
            "fx_journal_id": "journal",
            "fx_reversal_id": "journal",
        },
        CheckConstraint(
            "amount > 0 AND debt_base_amount >= 0 AND credit_base_amount >= 0",
            name="allocation_amount",
        ),
        CheckConstraint("debt_item_id <> credit_item_id", name="allocation_distinct"),
        CheckConstraint(
            "reversal_date IS NULL OR reversal_date >= posting_date", name="allocation_dates"
        ),
        Index(
            "ix_allocation_debt", "tenant_id", "company_id", "debt_item_id", "posting_date", "id"
        ),
        Index(
            "ix_allocation_credit",
            "tenant_id",
            "company_id",
            "credit_item_id",
            "posting_date",
            "id",
        ),
    )
    debt_item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    credit_item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    debt_base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    credit_base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    fx_journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reversal_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fx_reversal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


SUBLEDGER_MODELS = (OpeningBatch, SourceDocument, OpenItem, Allocation)
