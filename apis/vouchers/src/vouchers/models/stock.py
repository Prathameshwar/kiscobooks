"""Reusable native physical capture, shared by stock voucher kinds.

The common item detail remains the quantity/item authority. These tables capture
physical dimensions, reviewed inward value, original claims and selected unit IDs;
they never own stock balances, carrying costs or a second posting lifecycle.
"""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Money, Uuid7
from sqlalchemy import JSON, CheckConstraint, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vouchers.models.core import Record


class VoucherStockContext(Record, Base):
    __tablename__ = "voucher_stock_context"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_stock_context_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", name="uq_voucher_stock_context_revision"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_stock_context_revision",
        ),
        CheckConstraint(
            "schema_version = 1 AND row_version > 0", name="voucher_stock_context_version"
        ),
        CheckConstraint(
            "action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',"
            "'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT','PURCHASE_INVOICE')",
            name="voucher_stock_context_action",
        ),
        CheckConstraint(
            "(action = 'OPENING' AND opening_mode IS NOT NULL AND "
            "opening_mode IN ('COMBINED','LINKED_GL')) OR "
            "(action <> 'OPENING' AND opening_mode IS NULL)",
            name="voucher_stock_context_opening",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    opening_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    opening_control_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class VoucherStockDetail(Record, Base):
    __tablename__ = "voucher_stock_detail"
    count: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_stock_detail_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "id", name="uq_voucher_stock_detail_owner"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "line_id", name="uq_voucher_stock_detail_line"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "voucher_stock_context.tenant_id",
                "voucher_stock_context.company_id",
                "voucher_stock_context.revision_id",
            ],
            name="fk_voucher_stock_detail_context",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id", "line_id"],
            [
                "voucher_line.tenant_id",
                "voucher_line.company_id",
                "voucher_line.revision_id",
                "voucher_line.id",
            ],
            name="fk_voucher_stock_detail_line",
        ),
        CheckConstraint("row_version > 0", name="voucher_stock_detail_version"),
        CheckConstraint(
            "(received_value IS NULL AND zero_value_reason IS NULL) OR "
            "(received_value = 0 AND zero_value_reason IS NOT NULL) OR "
            "(received_value > 0 AND zero_value_reason IS NULL)",
            name="voucher_stock_detail_value",
        ),
        Index(
            "ix_voucher_stock_detail_source", "tenant_id", "company_id", "source_movement_id", "id"
        ),
        Index("ix_voucher_stock_detail_warehouse", "tenant_id", "company_id", "warehouse_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    received_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    zero_value_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    destination_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    destination_bin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    source_movement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    opening_journal_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    opening: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quantity_entry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class VoucherStockUnit(Record, Base):
    __tablename__ = "voucher_stock_unit"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_stock_unit_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "unit_id", name="uq_voucher_stock_unit_once"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "stock_detail_id",
            "sequence",
            name="uq_voucher_stock_unit_sequence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id", "stock_detail_id"],
            [
                "voucher_stock_detail.tenant_id",
                "voucher_stock_detail.company_id",
                "voucher_stock_detail.revision_id",
                "voucher_stock_detail.id",
            ],
            name="fk_voucher_stock_unit_detail",
        ),
        Index(
            "ix_voucher_stock_unit_detail",
            "tenant_id",
            "company_id",
            "revision_id",
            "stock_detail_id",
        ),
        CheckConstraint(
            "sequence BETWEEN 1 AND 200 AND row_version > 0", name="voucher_stock_unit_sequence"
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    stock_detail_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
