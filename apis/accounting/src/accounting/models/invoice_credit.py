"""Immutable input-credit instructions and committed component histories."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import Boolean, CheckConstraint, Date, Index, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.invoice import detail, reference
from accounting.models.masters import Record


class InvoiceCreditAction(Record):
    __tablename__ = "invoice_credit_action"
    __table_args__ = detail(
        "invoice_credit_action",
        reference("invoice_credit_action", "component_id", "invoice_tax_component", invoice=True),
        reference("invoice_credit_action", "journal_id", "journal"),
        reference("invoice_credit_action", "offset_account_id", "account"),
        reference("invoice_credit_action", "cash_deposit_line_id", "journal_line"),
        UniqueConstraint("tenant_id", "company_id", "journal_id"),
        Index(
            "ix_invoice_credit_action_component", "tenant_id", "company_id", "component_id", "id"
        ),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint(
            "kind IN ('VERIFY','CLAIM','BLOCK','REVERSE_PAYMENT',"
            "'RECLAIM_PAYMENT','RCM_DISCHARGE')",
            name="kind",
        ),
        CheckConstraint("LENGTH(evidence_sha256) = 64", name="evidence_hash"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    expected_event_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    offset_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    cash_deposit_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    annual_return_filed_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    document_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supply_received: Mapped[bool] = mapped_column(Boolean, nullable=False)
    business_use: Mapped[bool] = mapped_column(Boolean, nullable=False)
    restrictions_checked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supplier_report_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tax_payment_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    return_filed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supplier_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reference: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class InvoiceCreditEvent(Record):
    __tablename__ = "invoice_credit_event"
    __table_args__ = detail(
        "invoice_credit_event",
        reference("invoice_credit_event", "action_id", "invoice_credit_action", invoice=True),
        UniqueConstraint("tenant_id", "company_id", "action_id"),
        Index("ix_invoice_credit_event_history", "tenant_id", "company_id", "invoice_id", "id"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


INVOICE_CREDIT_MODELS = (InvoiceCreditAction, InvoiceCreditEvent)


@event.listens_for(Session, "before_flush")
def immutable_credit_history(db: Session, context: object, instances: object) -> None:
    if any(
        isinstance(row, INVOICE_CREDIT_MODELS) and db.is_modified(row) for row in db.dirty
    ) or any(isinstance(row, INVOICE_CREDIT_MODELS) for row in db.deleted):
        raise ConflictError("input-credit instructions and committed events are immutable")
