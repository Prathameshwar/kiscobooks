"""Bank statement evidence, reviewed allocations and frozen reconciliation periods."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, cast

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.orm.state import InstanceState

from accounting.models.masters import Record


class BankStatementMapping(Record):
    __tablename__ = "bank_statement_mapping"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bs_mapping_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_bs_mapping_account",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "account_id", "revision", name="uq_bs_mapping_revision"
        ),
        Index("ix_statement_mapping_account", "tenant_id", "company_id", "account_id", "revision"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    columns: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class BankStatementImport(Record):
    __tablename__ = "bank_statement_import"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bs_import_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_bs_import_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "mapping_id"],
            [
                "bank_statement_mapping.tenant_id",
                "bank_statement_mapping.company_id",
                "bank_statement_mapping.id",
            ],
            name="fk_bs_import_mapping",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "account_id", "file_sha256", name="uq_bs_import_file"
        ),
        Index("ix_statement_import_account", "tenant_id", "company_id", "account_id", "id"),
        CheckConstraint(
            "status IN ('PREVIEW','COMMITTED','REJECTED')", name="statement_import_status"
        ),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    mapping_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_to: Mapped[dt.date] = mapped_column(Date, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Money, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    review_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class BankStatementEntry(Record):
    __tablename__ = "bank_statement_entry"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bs_entry_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "import_id"],
            [
                "bank_statement_import.tenant_id",
                "bank_statement_import.company_id",
                "bank_statement_import.id",
            ],
            name="fk_bs_entry_import",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "import_id", "line_number", name="uq_bs_entry_line"
        ),
        Index(
            "ix_statement_entry_account",
            "tenant_id",
            "company_id",
            "account_id",
            "transaction_date",
            "id",
        ),
        Index(
            "ix_statement_entry_external", "tenant_id", "company_id", "account_id", "transaction_id"
        ),
        CheckConstraint("side IN ('DEBIT','CREDIT')", name="statement_entry_side"),
        CheckConstraint("amount > 0", name="statement_entry_amount"),
        CheckConstraint(
            "review_status IN ('NEW','EXISTING','AMBIGUOUS','ACCEPTED')",
            name="statement_entry_review",
        ),
        MARIADB_TABLE_ARGS,
    )
    import_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(12), nullable=False)
    running_balance: Mapped[Decimal | None] = mapped_column(Money, nullable=True)


class BankMatchEvent(Record):
    __tablename__ = "bank_match_event"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bank_match_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "statement_entry_id"],
            [
                "bank_statement_entry.tenant_id",
                "bank_statement_entry.company_id",
                "bank_statement_entry.id",
            ],
            name="fk_bank_match_entry",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "instrument_id"],
            ["bank_instrument.tenant_id", "bank_instrument.company_id", "bank_instrument.id"],
            name="fk_bank_match_instrument",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "reverses_id"],
            ["bank_match_event.tenant_id", "bank_match_event.company_id", "bank_match_event.id"],
            name="fk_bank_match_reversal",
        ),
        UniqueConstraint("tenant_id", "company_id", "reverses_id", name="uq_bank_match_reversal"),
        Index("ix_match_statement", "tenant_id", "company_id", "statement_entry_id", "id"),
        Index("ix_match_instrument", "tenant_id", "company_id", "instrument_id", "id"),
        CheckConstraint("amount > 0", name="bank_match_amount"),
        MARIADB_TABLE_ARGS,
    )
    statement_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    bank_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class BankReconciliationSession(Record):
    __tablename__ = "bank_reconciliation_session"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bank_session_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_bank_session_account",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "account_id",
            "period_from",
            "period_to",
            "generation",
            name="uq_bank_session_period",
        ),
        Index(
            "ix_bank_session_account", "tenant_id", "company_id", "account_id", "period_to", "id"
        ),
        CheckConstraint("status IN ('DRAFT','FINALIZED','AMENDED')", name="bank_session_status"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_to: Mapped[dt.date] = mapped_column(Date, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class BankOpeningItem(Record):
    """Reviewed cutover identity for a booked but not yet bank-cleared instrument."""

    __tablename__ = "bank_opening_item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bank_opening_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_bank_opening_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "instrument_id"],
            ["bank_instrument.tenant_id", "bank_instrument.company_id", "bank_instrument.id"],
            name="fk_bank_opening_instrument",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "account_id",
            "instrument_id",
            name="uq_bank_opening_instrument",
        ),
        Index(
            "ix_bank_opening_account", "tenant_id", "company_id", "account_id", "cutoff_date", "id"
        ),
        CheckConstraint("amount > 0", name="bank_opening_amount"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    cutoff_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class BankReconciliationPolicy(Record):
    """Immutable per-account review mode and candidate window revision."""

    __tablename__ = "bank_reconciliation_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bank_policy_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_bank_policy_account",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "account_id", "revision", name="uq_bank_policy_revision"
        ),
        Index("ix_bank_policy_account", "tenant_id", "company_id", "account_id", "revision"),
        CheckConstraint("mode IN ('MANUAL_ONLY','SUGGEST_AND_REVIEW')", name="bank_policy_mode"),
        CheckConstraint("match_window_days BETWEEN 0 AND 90", name="bank_policy_window"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    match_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    require_separate_reviewer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class BankAdjustmentProposal(Record):
    """Reviewed bank-only exception; only the ordinary voucher path may post money."""

    __tablename__ = "bank_adjustment_proposal"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_bank_proposal_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "statement_entry_id"],
            [
                "bank_statement_entry.tenant_id",
                "bank_statement_entry.company_id",
                "bank_statement_entry.id",
            ],
            name="fk_bank_proposal_entry",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "statement_entry_id", name="uq_bank_proposal_entry"
        ),
        Index("ix_bank_proposal_account", "tenant_id", "company_id", "account_id", "status", "id"),
        CheckConstraint(
            "kind IN ('PAYMENT','RECEIPT','CONTRA','JOURNAL')", name="bank_proposal_kind"
        ),
        CheckConstraint(
            "status IN ('PREPARED','REJECTED','RESOLVED')", name="bank_proposal_status"
        ),
        CheckConstraint("amount > 0", name="bank_proposal_amount"),
        MARIADB_TABLE_ARGS,
    )
    statement_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    voucher_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


BANK_RECONCILIATION_MODELS = (
    BankStatementMapping,
    BankStatementImport,
    BankStatementEntry,
    BankMatchEvent,
    BankReconciliationSession,
    BankOpeningItem,
    BankReconciliationPolicy,
    BankAdjustmentProposal,
)


@event.listens_for(Session, "before_flush")
def protect_bank_reconciliation_history(db: Session, context: object, instances: object) -> None:
    frozen = (BankStatementMapping, BankMatchEvent, BankOpeningItem, BankReconciliationPolicy)
    mutable = (
        BankStatementImport,
        BankStatementEntry,
        BankReconciliationSession,
        BankAdjustmentProposal,
    )
    for row in db.dirty:
        if isinstance(row, frozen) and db.is_modified(row):
            raise ConflictError("bank reconciliation evidence is immutable")
        if isinstance(row, mutable) and db.is_modified(row):
            state = cast(InstanceState[Any], inspect(row))
            changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
            allowed = {
                "row_version",
                "updated_at",
                "updated_by",
                "status",
                "review_status",
                "review_reason",
                "reason",
                "voucher_id",
                "decision_reason",
            }
            if changed - allowed:
                raise ConflictError("bank reconciliation source fields are immutable")
    if any(isinstance(row, frozen + mutable) for row in db.deleted):
        raise ConflictError("bank reconciliation evidence cannot be deleted")
