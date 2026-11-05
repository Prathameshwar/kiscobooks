"""Opening balances captured with a party import, held until the opening declaration takes them."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class PartyOpeningBalance(Record):
    """One staged line: a party ledger account, a side, an amount and exactly one document.

    A line never touches the ledger. The opening workspace copies it into a declaration the actor
    reviews and balances; this row only keeps what the import was given, and whether it was
    withdrawn. `source_key` is also the declaration entry's source key, which is how the workspace
    knows the line is already included.
    """

    __tablename__ = "party_opening_balance"
    __table_args__ = constraints(
        "party_opening_balance",
        {"party_id": "party", "account_id": "account"},
        UniqueConstraint(
            "tenant_id", "company_id", "source_key", name="uq_party_opening_balance_source"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "account_id", name="uq_party_opening_balance_account"
        ),
        Index("ix_party_opening_balance_status", "tenant_id", "company_id", "status", "id"),
        Index("ix_party_opening_balance_party", "tenant_id", "company_id", "party_id", "id"),
        CheckConstraint("status IN ('PENDING', 'WITHDRAWN')", name="party_opening_balance_status"),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="party_opening_balance_role"),
        CheckConstraint("side IN ('DEBIT', 'CREDIT')", name="party_opening_balance_side"),
        CheckConstraint(
            "amount > 0 AND base_amount > 0 AND exchange_rate > 0",
            name="party_opening_balance_values",
        ),
        CheckConstraint(
            "document_kind IS NULL OR "
            "document_kind IN ('ON_ACCOUNT', 'INVOICE', 'BILL', 'ADVANCE', 'CREDIT_NOTE')",
            name="party_opening_balance_kind",
        ),
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(19, 8, asdecimal=True), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    document_kind: Mapped[str | None] = mapped_column(String(20))
    document_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    document_date: Mapped[dt.date | None] = mapped_column(Date)
    due_date: Mapped[dt.date | None] = mapped_column(Date)


# The staged facts are evidence of what an actor was shown and approved at import time; only the
# lifecycle may change, and a row is never deleted.
_IMMUTABLE = frozenset(
    {
        "party_id",
        "role",
        "account_id",
        "source_key",
        "side",
        "currency",
        "amount",
        "exchange_rate",
        "base_amount",
        "document_kind",
        "document_reference",
        "document_date",
        "due_date",
        "company_id",
        "tenant_id",
    }
)


@event.listens_for(Session, "before_flush")
def immutable_party_opening(session: Session, flush_context: object, instances: object) -> None:
    for row in session.deleted:
        if isinstance(row, PartyOpeningBalance):
            raise ConflictError("staged party opening balances cannot be deleted; withdraw them")
    for row in session.dirty:
        if isinstance(row, PartyOpeningBalance):
            state = inspect(row)
            if any(state.attrs[key].history.has_changes() for key in _IMMUTABLE):
                raise ConflictError("staged party opening balances are immutable; withdraw them")
            history = state.attrs.status.history
            if history.has_changes() and history.deleted and history.deleted[0] == "WITHDRAWN":
                raise ConflictError("a withdrawn party opening balance cannot be restored")


PARTY_OPENING_MODELS = (PartyOpeningBalance,)
