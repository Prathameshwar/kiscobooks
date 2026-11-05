"""Immutable common invoice calculation facts, shared by all financial invoice kinds."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, Quantity, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.schema import conv

from accounting.models.masters import Record


def scope(*extra: Any) -> tuple[Any, ...]:
    return (UniqueConstraint("tenant_id", "company_id", "id"), *extra, MARIADB_TABLE_ARGS)


def reference(name: str, field: str, target: str, *, invoice: bool = False) -> ForeignKeyConstraint:
    fields = ["tenant_id", "company_id", *(["invoice_id"] if invoice else []), field]
    targets = ["tenant_id", "company_id", *(["invoice_id"] if invoice else []), "id"]
    return ForeignKeyConstraint(
        fields, [f"{target}.{key}" for key in targets], name=f"fk_{name}_{field}"
    )


def detail(name: str, *extra: Any) -> tuple[Any, ...]:
    return scope(
        UniqueConstraint("tenant_id", "company_id", "invoice_id", "id"),
        reference(name, "invoice_id", "invoice_record"),
        *extra,
    )


class InvoiceRecord(Record):
    __tablename__ = "invoice_record"
    __table_args__ = scope(
        reference("invoice_record", "intent_id", "voucher_money_intent"),
        reference("invoice_record", "party_account_id", "account"),
        reference("invoice_record", "source_invoice_id", "invoice_record"),
        UniqueConstraint("tenant_id", "company_id", "intent_id"),
        CheckConstraint("calculation_version = 1", name="calculation_version"),
        CheckConstraint("kind IN ('SALES','PURCHASE','CREDIT_NOTE','DEBIT_NOTE')", name="kind"),
        CheckConstraint(
            "(kind IN ('SALES','PURCHASE') AND source_invoice_id IS NULL) OR "
            "(kind IN ('CREDIT_NOTE','DEBIT_NOTE') AND source_invoice_id IS NOT NULL)",
            name=conv("source_kind"),
        ),
        CheckConstraint(
            "commercial_total >= 0 AND tax_total >= 0 AND charged_tax_total >= 0 AND payable > 0",
            name="amounts",
        ),
        CheckConstraint(
            "LENGTH(calculation_hash) = 64 AND LENGTH(configuration_hash) = 64 "
            "AND LENGTH(company_configuration_hash) = 64",
            name="hashes",
        ),
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    calculation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    calculation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    company_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    document_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    party_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bill_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    commercial_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    charged_tax_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    rounding: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    supplier_declared_total: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    supplier_difference: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    supplier_difference_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class InvoiceSupplyFact(Record):
    __tablename__ = "invoice_supply_fact"
    __table_args__ = detail(
        "invoice_supply_fact",
        reference("invoice_supply_fact", "account_id", "account"),
        UniqueConstraint("tenant_id", "company_id", "invoice_id", "line_key"),
        CheckConstraint(
            "entered >= 0 AND commercial >= 0 AND taxable >= 0 AND payable >= 0", name="amounts"
        ),
        CheckConstraint("date_contract_version = 2", name="date_version"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supply_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    entered: Mapped[Decimal] = mapped_column(Money, nullable=False)
    commercial: Mapped[Decimal] = mapped_column(Money, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_rounding: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_profile: Mapped[str] = mapped_column(String(40), nullable=False)
    date_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_point_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    tax_point_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    service_completion_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    company_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(10), nullable=True)
    supply_context: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    treatment: Mapped[str] = mapped_column(String(10), nullable=False)
    reverse_charge: Mapped[bool] = mapped_column(Boolean, nullable=False)
    credit_state: Mapped[str] = mapped_column(String(20), nullable=False)
    supplier_invoice_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_invoice_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # Frozen resolution evidence supplements the queryable statutory facts above.
    source_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class InvoiceComponentFact(Record):
    __tablename__ = "invoice_component_fact"
    __table_args__ = detail(
        "invoice_component_fact",
        UniqueConstraint("tenant_id", "company_id", "invoice_id", "component_key"),
        reference("invoice_component_fact", "account_id", "account"),
        CheckConstraint(
            "basis_amount >= 0 AND (basis_quantity IS NULL OR basis_quantity >= 0)", name="basis"
        ),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    effect: Mapped[str] = mapped_column(String(10), nullable=False)
    input_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    basis_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    basis_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    input_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    commercial_treatment: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_treatment: Mapped[str] = mapped_column(String(20), nullable=False)
    return_treatment: Mapped[str] = mapped_column(String(20), nullable=False)
    source_evidence: Mapped[str] = mapped_column(String(500), nullable=False)


class InvoiceAllocationFact(Record):
    __tablename__ = "invoice_allocation_fact"
    __table_args__ = detail(
        "invoice_allocation_fact",
        reference(
            "invoice_allocation_fact", "component_id", "invoice_component_fact", invoice=True
        ),
        reference("invoice_allocation_fact", "supply_id", "invoice_supply_fact", invoice=True),
        UniqueConstraint(
            "tenant_id", "company_id", "invoice_id", "component_id", "supply_id", "purpose"
        ),
        CheckConstraint("purpose IN ('COMMERCIAL','TAX_BASE','STOCK_COST')", name="purpose"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supply_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class InvoiceTaxComponent(Record):
    __tablename__ = "invoice_tax_component"
    __table_args__ = detail(
        "invoice_tax_component",
        reference("invoice_tax_component", "supply_id", "invoice_supply_fact", invoice=True),
        UniqueConstraint("tenant_id", "company_id", "invoice_id", "supply_id", "component_key"),
        CheckConstraint("code IN ('CGST','SGST','UTGST','IGST','CESS')", name="code"),
        CheckConstraint("basis >= 0 AND amount >= 0 AND percentage >= 0", name="amounts"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supply_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component_key: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(5), nullable=False)
    basis: Mapped[Decimal] = mapped_column(Money, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(19, 8), nullable=False)
    supplier_charged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rounding_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)


class InvoicePostingLine(Record):
    """Link accepted source keys to native GL lines without a second amount store."""

    __tablename__ = "invoice_posting_line"
    __table_args__ = detail(
        "invoice_posting_line",
        reference("invoice_posting_line", "journal_line_id", "journal_line"),
        reference(
            "invoice_posting_line", "tax_component_id", "invoice_tax_component", invoice=True
        ),
        UniqueConstraint("tenant_id", "company_id", "invoice_id", "line_key"),
        UniqueConstraint("tenant_id", "company_id", "journal_line_id"),
        CheckConstraint("source_version > 0 AND sequence > 0", name="version_sequence"),
        CheckConstraint("tracking IN ('NONE','NEW_REF','ON_ACCOUNT','ADVANCE')", name="tracking"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    tax_component_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    tax_purpose: Mapped[str | None] = mapped_column(String(30), nullable=True)
    line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    tracking: Mapped[str] = mapped_column(String(20), nullable=False)
    bill_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


INVOICE_MODELS = (
    InvoiceRecord,
    InvoiceSupplyFact,
    InvoiceComponentFact,
    InvoiceAllocationFact,
    InvoiceTaxComponent,
    InvoicePostingLine,
)


@event.listens_for(Session, "before_flush")
def protect_invoice_history(db: Session, context: object, instances: object) -> None:
    if any(isinstance(row, INVOICE_MODELS) and db.is_modified(row) for row in db.dirty) or any(
        isinstance(row, INVOICE_MODELS) for row in db.deleted
    ):
        raise ConflictError("invoice calculation facts are immutable; post a linked correction")
