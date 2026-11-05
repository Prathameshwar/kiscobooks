"""Common invoice/charge sections. Neither sales nor purchases own separate tables."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Money, Quantity, Uuid7
from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from vouchers.models.core import Record


def scope(name: str, *extra: Any) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name=f"fk_{name}_revision",
        ),
        *extra,
        MARIADB_TABLE_ARGS,
    )


def reference(name: str, field: str, target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", "revision_id", field],
        [f"{target}.tenant_id", f"{target}.company_id", f"{target}.revision_id", f"{target}.id"],
        name=f"fk_{name}_{field}",
    )


class VoucherInvoiceDetail(Record, Base):
    __tablename__ = "voucher_invoice_detail"
    __table_args__ = scope(
        "voucher_invoice_detail",
        UniqueConstraint("tenant_id", "company_id", "revision_id"),
        # Duplicate supplier-bill detection for imports and entry.
        Index(
            "ix_voucher_invoice_supplier_number",
            "tenant_id",
            "company_id",
            "supplier_invoice_number",
        ),
        CheckConstraint(
            "accepted_calculation_hash IS NULL OR LENGTH(accepted_calculation_hash) = 64",
            name="calculation_hash",
        ),
        CheckConstraint(
            "schema_version = 1 AND date_contract_version = 2", name="voucher_invoice_versions"
        ),
        CheckConstraint(
            "exchange_rate > 0 AND party_account_version > 0", name="voucher_invoice_values"
        ),
        CheckConstraint(
            "rounding_increment IS NULL OR rounding_increment > 0", name="voucher_invoice_rounding"
        ),
        CheckConstraint(
            "supplier_declared_total IS NULL OR supplier_declared_total >= 0",
            name="voucher_invoice_declared",
        ),
        CheckConstraint(
            "payable_total IS NULL OR payable_total >= 0",
            name="voucher_invoice_payable_total",
        ),
        CheckConstraint(
            "(rounding_account_id IS NULL AND rounding_account_version IS NULL) OR "
            "(rounding_account_id IS NOT NULL AND rounding_account_version IS NOT NULL "
            "AND rounding_account_version > 0)",
            name="voucher_invoice_round_account",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_calculation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_account_version: Mapped[int] = mapped_column(Integer, nullable=False)
    bill_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(19, 8), nullable=False)
    rounding_increment: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    rounding_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    rounding_account_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supplier_declared_total: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    supplier_difference_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    date_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    company_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(10), nullable=True)
    service_completion_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    supplier_invoice_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_invoice_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    withholding_section_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    payable_total: Mapped[Decimal | None] = mapped_column(Money, nullable=True)


class VoucherSupplyDetail(Record, Base):
    __tablename__ = "voucher_supply_detail"
    __table_args__ = scope(
        "voucher_supply_detail",
        reference("voucher_supply_detail", "line_id", "voucher_line"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "line_id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "sequence"),
        CheckConstraint(
            "amount >= 0 AND price_denominator > 0 AND (unit_price IS NULL OR unit_price >= 0)",
            name="voucher_supply_amounts",
        ),
        CheckConstraint("account_version > 0 AND sequence > 0", name="voucher_supply_version"),
        CheckConstraint("supply_kind IN ('ACCOUNT','SERVICE','GOODS')", name="voucher_supply_kind"),
        CheckConstraint(
            "price_basis IN ('NET_EXCL_TAX','GROSS_INCL_TAX')", name="voucher_supply_price_basis"
        ),
        CheckConstraint(
            "(promotion_revision_id IS NULL AND promotion_version IS NULL) OR "
            "(promotion_revision_id IS NOT NULL AND promotion_version IS NOT NULL "
            "AND promotion_version > 0)",
            name="voucher_supply_promotion",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_version: Mapped[int] = mapped_column(Integer, nullable=False)
    supply_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    item_line_key: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    price_denominator: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    free_purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    free_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    promotion_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    promotion_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # B24: a purchased goods line whose GST cannot be claimed, and why (migrations 0114-0115).
    input_credit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    input_credit_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class VoucherSupplyTaxContext(Record, Base):
    __tablename__ = "voucher_supply_tax_context"
    __table_args__ = scope(
        "voucher_supply_tax_context",
        reference("voucher_supply_tax_context", "supply_id", "voucher_supply_detail"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "supply_id"),
        CheckConstraint("date_contract_version = 2", name="date_version"),
        CheckConstraint(
            "profile IN ('UNTAXED_ACCOUNT','INDIA_DOMESTIC_SERVICE','INDIA_DOMESTIC_SERVICE_RCM',"
            "'INDIA_DOMESTIC_GOODS')",
            name="profile",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supply_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    date_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    company_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(10), nullable=True)
    service_completion_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    supplier_invoice_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_invoice_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    withholding_section_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class VoucherSupplyQuantity(Record, Base):
    __tablename__ = "voucher_supply_quantity"
    __table_args__ = scope(
        "voucher_supply_quantity",
        reference("voucher_supply_quantity", "supply_id", "voucher_supply_detail"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "supply_id", "basis"),
        CheckConstraint("quantity >= 0", name="voucher_supply_quantity_amount"),
        CheckConstraint(
            "basis IN ('ACTUAL','BILLED','ACCEPTED','RETURNED','MEASURED')",
            name="voucher_supply_quantity_basis",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supply_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    basis: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class VoucherChargeDetail(Record, Base):
    __tablename__ = "voucher_charge_detail"
    __table_args__ = scope(
        "voucher_charge_detail",
        reference("voucher_charge_detail", "line_id", "voucher_line"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "line_id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "sequence"),
        CheckConstraint(
            "denominator > 0 AND ((input_kind = 'PERCENT' AND value IS NULL "
            "AND percentage IS NOT NULL AND percentage >= 0) OR (input_kind <> 'PERCENT' "
            "AND percentage IS NULL AND value IS NOT NULL AND value >= 0))",
            name="voucher_charge_values",
        ),
        CheckConstraint(
            "scope IN ('LINE','SELECTED_LINES','INVOICE')", name="voucher_charge_scope"
        ),
        CheckConstraint("effect IN ('ADD','DEDUCT')", name="voucher_charge_effect"),
        CheckConstraint(
            "input_kind IN ('FIXED','PERCENT','PER_QUANTITY')", name="voucher_charge_input"
        ),
        CheckConstraint(
            "(account_id IS NULL AND account_version IS NULL) OR "
            "(account_id IS NOT NULL AND account_version IS NOT NULL AND account_version > 0)",
            name="voucher_charge_account",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    effect: Mapped[str] = mapped_column(String(6), nullable=False)
    input_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(19, 8), nullable=True)
    amount_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    allocation_basis: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity_basis: Mapped[str | None] = mapped_column(String(10), nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    denominator: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    commercial_treatment: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_treatment: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_allocation_basis: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cost_allocation_basis: Mapped[str] = mapped_column(String(10), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    account_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_evidence: Mapped[str] = mapped_column(String(500), nullable=False)
    return_treatment: Mapped[str] = mapped_column(String(20), nullable=False)


class VoucherChargeTarget(Record, Base):
    __tablename__ = "voucher_charge_target"
    __table_args__ = scope(
        "voucher_charge_target",
        reference("voucher_charge_target", "charge_id", "voucher_charge_detail"),
        reference("voucher_charge_target", "supply_id", "voucher_supply_detail"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "charge_id", "purpose", "supply_id"
        ),
        CheckConstraint(
            "purpose IN ('BASIS','STOCK_COST','TAX_BASE')", name="voucher_charge_target_purpose"
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    charge_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supply_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(15), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)


class VoucherChargeDependency(Record, Base):
    __tablename__ = "voucher_charge_dependency"
    __table_args__ = scope(
        "voucher_charge_dependency",
        reference("voucher_charge_dependency", "charge_id", "voucher_charge_detail"),
        reference("voucher_charge_dependency", "depends_on_id", "voucher_charge_detail"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "charge_id", "depends_on_id"),
        CheckConstraint("charge_id <> depends_on_id", name="voucher_charge_dependency_distinct"),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    charge_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    depends_on_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
