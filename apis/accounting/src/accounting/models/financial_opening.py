"""Immutable declaration evidence and child journal links for the existing opening owner."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class FinancialOpeningRevision(Record):
    __tablename__ = "financial_opening_revision"
    __table_args__ = constraints(
        "financial_opening_revision",
        {"batch_id": "opening_batch"},
        UniqueConstraint(
            "tenant_id", "company_id", "batch_id", "revision", name="uq_fin_open_revision"
        ),
        CheckConstraint("revision > 0", name="fin_open_revision_positive"),
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    header: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FinancialOpeningEntry(Record):
    __tablename__ = "financial_opening_entry"
    __table_args__ = constraints(
        "financial_opening_entry",
        {"revision_id": "financial_opening_revision", "account_id": "account", "party_id": "party"},
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "ordinal", name="uq_fin_open_entry_order"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "source_key", name="uq_fin_open_entry_source"
        ),
        Index("ix_fin_open_entry_revision", "tenant_id", "company_id", "revision_id", "id"),
        Index(
            "ix_fin_open_entry_account",
            "tenant_id",
            "company_id",
            "revision_id",
            "account_id",
            "id",
        ),
        Index(
            "ix_fin_open_entry_party", "tenant_id", "company_id", "revision_id", "party_id", "id"
        ),
        CheckConstraint(
            "ordinal > 0 AND amount > 0 AND base_amount > 0 AND document_count >= 0",
            name="fin_open_entry_values",
        ),
        CheckConstraint("side IN ('DEBIT','CREDIT')", name="fin_open_entry_side"),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    role: Mapped[str | None] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FinancialOpeningChunk(Record):
    __tablename__ = "financial_opening_chunk"
    __table_args__ = constraints(
        "financial_opening_chunk",
        {
            "batch_id": "opening_batch",
            "revision_id": "financial_opening_revision",
            "journal_id": "journal",
        },
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "ordinal", name="uq_fin_open_chunk_order"
        ),
        UniqueConstraint("tenant_id", "company_id", "journal_id", name="uq_fin_open_chunk_journal"),
        Index("ix_fin_open_chunk_batch", "tenant_id", "company_id", "batch_id", "id"),
        CheckConstraint("ordinal > 0", name="fin_open_chunk_positive"),
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FinancialOpeningImport(Record):
    __tablename__ = "financial_opening_import"
    __table_args__ = constraints(
        "financial_opening_import",
        {"batch_id": "opening_batch"},
        UniqueConstraint("tenant_id", "company_id", "source_key", name="uq_fin_open_import_source"),
        Index("ix_fin_open_import_hash", "tenant_id", "company_id", "input_hash", "id"),
        Index("ix_fin_open_import_state", "tenant_id", "company_id", "state", "id"),
        CheckConstraint(
            "state IN ('STAGED','READY','COMMITTED','BLOCKED','CANCELLED')",
            name="fin_open_import_state",
        ),
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    review_hash: Mapped[str | None] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


FINANCIAL_OPENING_MODELS = (
    FinancialOpeningRevision,
    FinancialOpeningEntry,
    FinancialOpeningChunk,
    FinancialOpeningImport,
)


@event.listens_for(Session, "before_flush")
def immutable_evidence(session: Session, flush_context: Any, instances: Any) -> None:
    for row in session.deleted:
        if isinstance(row, FINANCIAL_OPENING_MODELS):
            raise ConflictError("financial opening evidence cannot be deleted")
    for row in session.dirty:
        if isinstance(row, FinancialOpeningImport):
            state = inspect(row)
            if any(
                state.attrs[key].history.has_changes()
                for key in ("source_key", "input_hash", "document", "company_id", "tenant_id")
            ):
                raise ConflictError("opening import source evidence is immutable")
        if isinstance(
            row, FinancialOpeningEntry | FinancialOpeningRevision
        ) and session.is_modified(row):
            raise ConflictError("financial opening declarations are immutable; create a revision")
        if isinstance(row, FinancialOpeningChunk):
            changed = {
                attribute.key for attribute in inspect(row).attrs if attribute.history.has_changes()
            }
            if changed - {"journal_id", "row_version", "updated_at", "updated_by"}:
                raise ConflictError("native opening execution evidence is immutable")
            history = inspect(row).attrs.journal_id.history
            if history.has_changes() and history.deleted and history.deleted[0] is not None:
                raise ConflictError("an opening chunk cannot be attached to another journal")
