"""Common posting intents and banking evidence for every ordinary money voucher."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record


class VoucherMoneyIntent(Record):
    __tablename__ = "voucher_money_intent"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "execution_id"),
        UniqueConstraint("tenant_id", "company_id", "journal_id"),
        Index("ix_money_intent_source", "tenant_id", "company_id", "voucher_id", "status"),
        Index("ix_money_intent_pending", "tenant_id", "company_id", "status", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "journal_id"],
            ["journal.tenant_id", "journal.company_id", "journal.id"],
            name="fk_money_intent_journal",
        ),
        CheckConstraint(
            "status IN ('PREPARED', 'COMMITTED', 'CANCELLED')", name="money_intent_status"
        ),
        MARIADB_TABLE_ARGS,
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Accepted transport evidence; amounts are posted into native journal/open-item rows.
    command: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class BankInstrument(Record):
    __tablename__ = "bank_instrument"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "intent_id", "tender_key"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "intent_id"],
            [
                "voucher_money_intent.tenant_id",
                "voucher_money_intent.company_id",
                "voucher_money_intent.id",
            ],
            name="fk_bank_instrument_intent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "journal_line_id"],
            ["journal_line.tenant_id", "journal_line.company_id", "journal_line.id"],
            name="fk_bank_instrument_line",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_bank_instrument_account",
        ),
        CheckConstraint("amount > 0", name="bank_instrument_positive"),
        Index(
            "ix_bank_instrument_book", "tenant_id", "company_id", "account_id", "booking_date", "id"
        ),
        Index("ix_bank_instrument_page", "tenant_id", "company_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    intent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    journal_line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    tender_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    instrument_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    booking_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    recognition: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class BankInstrumentEvent(Record):
    __tablename__ = "bank_instrument_event"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "instrument_id"],
            ["bank_instrument.tenant_id", "bank_instrument.company_id", "bank_instrument.id"],
            name="fk_bank_event_instrument",
        ),
        Index(
            "ix_bank_event_history", "tenant_id", "company_id", "instrument_id", "event_date", "id"
        ),
        CheckConstraint(
            "action IN ('BOOKED', 'PRESENTED', 'CLEARED', 'DISHONOURED', "
            "'RECONCILED', 'UNRECONCILED', 'REVERSED')",
            name="bank_event_action",
        ),
        MARIADB_TABLE_ARGS,
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


@event.listens_for(Session, "before_flush")
def protect_money_history(db: Session, context: object, instances: object) -> None:
    for row in db.dirty:
        if isinstance(
            row, BankInstrument | BankInstrumentEvent | VoucherMoneyAllocation
        ) and db.is_modified(row):
            raise ConflictError("bank evidence is immutable; append a dated event")
        if isinstance(row, VoucherMoneyIntent):
            state = inspect(row)
            assert state is not None
            changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
            if changed - {"status", "row_version", "updated_at", "updated_by"}:
                raise ConflictError("posting intent evidence is immutable")
            history = state.attrs.status.history
            if history.deleted and history.deleted[0] in {"COMMITTED", "CANCELLED"}:
                raise ConflictError("terminal posting intent is immutable")
    if any(
        isinstance(
            row, VoucherMoneyIntent | BankInstrument | BankInstrumentEvent | VoucherMoneyAllocation
        )
        for row in db.deleted
    ):
        raise ConflictError("money evidence cannot be deleted")


class VoucherMoneyAllocation(Record):
    __tablename__ = "voucher_money_allocation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "intent_id", "allocation_key"),
        UniqueConstraint("tenant_id", "company_id", "allocation_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "intent_id"],
            [
                "voucher_money_intent.tenant_id",
                "voucher_money_intent.company_id",
                "voucher_money_intent.id",
            ],
            name="fk_money_allocation_intent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "allocation_id"],
            ["allocation.tenant_id", "allocation.company_id", "allocation.id"],
            name="fk_money_allocation_effect",
        ),
        MARIADB_TABLE_ARGS,
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    allocation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    allocation_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


VOUCHER_MONEY_MODELS = (
    VoucherMoneyIntent,
    BankInstrument,
    BankInstrumentEvent,
    VoucherMoneyAllocation,
)
