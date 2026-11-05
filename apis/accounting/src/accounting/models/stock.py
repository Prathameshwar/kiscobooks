"""Native company/warehouse stock authority, separate from prepared identities.

Balances, residuals and unit custody are guarded projections. Movement, origin,
cost and value histories retain the facts from which those projections reconcile.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, cast

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    Table,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import InstanceState, Mapped, Session, mapped_column

from accounting.models.masters import Record

ZERO_KEY = "X'00000000000000000000000000000000'"


class StockMoneyRecord(Record):
    __abstract__ = True
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


def constraints(name: str) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        Index(f"ix_{name}_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name=f"{name}_version"),
    )


def reference(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", column],
        [f"{target}.tenant_id", f"{target}.company_id", f"{target}.id"],
        name=name,
    )


class StockPosition(Record):
    __tablename__ = "stock_position"
    __table_args__ = (
        *constraints("stock_position"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "warehouse_id",
            "bin_key",
            "lot_key",
            "disposition",
            name="uq_stock_position_identity",
        ),
        reference("lot_id", "stock_lot", "fk_stock_position_lot"),
        CheckConstraint(
            f"(lot_id IS NULL AND lot_key = {ZERO_KEY}) OR "
            "(lot_id IS NOT NULL AND lot_key = lot_id)",
            name="stock_position_lot_key",
        ),
        CheckConstraint(
            f"(bin_id IS NULL AND bin_key = {ZERO_KEY}) OR "
            "(bin_id IS NOT NULL AND bin_key = bin_id)",
            name="stock_position_bin_key",
        ),
        CheckConstraint(
            "owner_kind = 'COMPANY' AND custody_kind IN ('WAREHOUSE','TRANSIT') "
            "AND disposition = 'USABLE'",
            name="stock_position_supported_scope",
        ),
        Index("ix_stock_position_item", "tenant_id", "company_id", "item_id", "warehouse_id", "id"),
        Index(
            "ix_stock_position_location", "tenant_id", "company_id", "warehouse_id", "bin_key", "id"
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    bin_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lot_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPANY")
    custody_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="WAREHOUSE")
    disposition: Mapped[str] = mapped_column(String(20), nullable=False, default="USABLE")


class StockBalance(Record):
    __tablename__ = "stock_balance"
    __table_args__ = (
        *constraints("stock_balance"),
        UniqueConstraint(
            "tenant_id", "company_id", "position_id", name="uq_stock_balance_position"
        ),
        reference("position_id", "stock_position", "fk_stock_balance_position"),
        CheckConstraint("quantity >= 0", name="stock_balance_nonnegative"),
        MARIADB_TABLE_ARGS,
    )
    position_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockAccountPolicy(Record):
    __tablename__ = "stock_account_policy"
    __table_args__ = (
        *constraints("stock_account_policy"),
        UniqueConstraint(
            "tenant_id", "company_id", "valid_from", name="uq_stock_account_policy_start"
        ),
        *(
            reference(column, "account", "fk_stock_policy_" + label)
            for column, label in (
                ("inventory_account_id", "inventory"),
                ("receipt_clearing_account_id", "receipt"),
                ("dispatch_clearing_account_id", "dispatch"),
                ("opening_offset_account_id", "opening"),
                ("variance_account_id", "variance"),
            )
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="stock_account_policy_dates"
        ),
        Index("ix_stock_account_policy_date", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    inventory_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    receipt_clearing_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    dispatch_clearing_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    opening_offset_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    variance_account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class StockPosting(Record):
    __tablename__ = "stock_posting"
    __table_args__ = (
        *constraints("stock_posting"),
        UniqueConstraint(
            "tenant_id", "company_id", "execution_id", name="uq_stock_posting_execution"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "operation_id", name="uq_stock_posting_operation"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "reverses_id", name="uq_stock_posting_reversal"
        ),
        reference("intent_id", "voucher_money_intent", "fk_stock_posting_intent"),
        reference("journal_id", "journal", "fk_stock_posting_journal"),
        reference("reverses_id", "stock_posting", "fk_stock_posting_reversal"),
        reference("account_policy_id", "stock_account_policy", "fk_stock_posting_policy"),
        CheckConstraint(
            "action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER',"
            "'TRANSFER_DISPATCH','TRANSFER_RECEIPT',"
            "'CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT','PURCHASE_INVOICE','REVERSAL')",
            name="stock_posting_action",
        ),
        Index("ix_stock_posting_date", "tenant_id", "company_id", "stock_date", "id"),
        Index("ix_stock_posting_source", "tenant_id", "company_id", "voucher_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    stock_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    account_policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class StockExecutionPlan(Record):
    """Immutable prepared evidence subordinate to the common voucher intent."""

    __tablename__ = "stock_execution_plan"
    __table_args__ = (
        *constraints("stock_execution_plan"),
        reference("intent_id", "voucher_money_intent", "fk_stock_execution_plan_intent"),
        UniqueConstraint(
            "tenant_id", "company_id", "intent_id", name="uq_stock_execution_plan_intent"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "execution_id", name="uq_stock_execution_plan_execution"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "source_fence_id", name="uq_stock_execution_plan_fence"
        ),
        Index(
            "ix_stock_execution_plan_expiry",
            "tenant_id",
            "company_id",
            "source_fence_expires_at",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_fence_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_fence_expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    effects: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class StockCostPool(StockMoneyRecord):
    __tablename__ = "stock_cost_pool"
    __table_args__ = (
        *constraints("stock_cost_pool"),
        UniqueConstraint(
            "tenant_id", "company_id", "item_id", "warehouse_id", name="uq_stock_cost_pool_identity"
        ),
        reference("last_posting_id", "stock_posting", "fk_stock_cost_pool_posting"),
        Index("ix_stock_cost_pool_location", "tenant_id", "company_id", "warehouse_id", "id"),
        CheckConstraint("method IN ('FIFO','MOVING_AVERAGE')", name="stock_cost_pool_method"),
        CheckConstraint(
            "quantity >= 0 AND value >= 0 AND (quantity > 0 OR value = 0)",
            name="stock_cost_pool_balance",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    last_stock_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    last_posting_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class StockMovement(Record):
    __tablename__ = "stock_movement"
    __table_args__ = (
        *constraints("stock_movement"),
        reference("posting_id", "stock_posting", "fk_stock_movement_posting"),
        reference("position_id", "stock_position", "fk_stock_movement_position"),
        reference("pool_id", "stock_cost_pool", "fk_stock_movement_pool"),
        reference("source_movement_id", "stock_movement", "fk_stock_movement_source"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "posting_id",
            "line_id",
            "leg",
            name="uq_stock_movement_source_leg",
        ),
        CheckConstraint("quantity <> 0 AND leg IN ('IN','OUT')", name="stock_movement_quantity"),
        CheckConstraint(
            "(leg = 'IN' AND quantity > 0) OR (leg = 'OUT' AND quantity < 0)",
            name="stock_movement_direction",
        ),
        Index("ix_stock_movement_position", "tenant_id", "company_id", "position_id", "id"),
        Index("ix_stock_movement_source", "tenant_id", "company_id", "source_movement_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    posting_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    position_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    pool_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    leg: Mapped[str] = mapped_column(String(3), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    source_movement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class StockReceiptOrigin(Record):
    __tablename__ = "stock_receipt_origin"
    __table_args__ = (
        *constraints("stock_receipt_origin"),
        reference("movement_id", "stock_movement", "fk_stock_origin_movement"),
        UniqueConstraint("tenant_id", "company_id", "movement_id", name="uq_stock_origin_movement"),
        CheckConstraint("quantity > 0", name="stock_origin_quantity"),
        MARIADB_TABLE_ARGS,
    )
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    received_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    history_known: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockOriginBalance(Record):
    __tablename__ = "stock_origin_balance"
    __table_args__ = (
        *constraints("stock_origin_balance"),
        reference("origin_id", "stock_receipt_origin", "fk_stock_origin_balance_origin"),
        reference("position_id", "stock_position", "fk_stock_origin_balance_position"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "origin_id",
            "position_id",
            name="uq_stock_origin_balance_position",
        ),
        Index("ix_stock_origin_balance_position", "tenant_id", "company_id", "position_id", "id"),
        Index(
            "ix_stock_origin_balance_remaining",
            "tenant_id",
            "company_id",
            "position_id",
            "quantity",
            "id",
        ),
        CheckConstraint("quantity >= 0", name="stock_origin_balance_quantity"),
        MARIADB_TABLE_ARGS,
    )
    origin_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    position_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockOriginAllocation(Record):
    __tablename__ = "stock_origin_allocation"
    __table_args__ = (
        *constraints("stock_origin_allocation"),
        reference("origin_id", "stock_receipt_origin", "fk_stock_origin_allocation_origin"),
        reference("movement_id", "stock_movement", "fk_stock_origin_allocation_movement"),
        UniqueConstraint(
            "tenant_id", "company_id", "movement_id", "origin_id", name="uq_stock_origin_allocation"
        ),
        CheckConstraint("quantity <> 0", name="stock_origin_allocation_quantity"),
        MARIADB_TABLE_ARGS,
    )
    origin_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockCostLayer(StockMoneyRecord):
    __tablename__ = "stock_cost_layer"
    __table_args__ = (
        *constraints("stock_cost_layer"),
        reference("pool_id", "stock_cost_pool", "fk_stock_cost_layer_pool"),
        reference("movement_id", "stock_movement", "fk_stock_cost_layer_movement"),
        UniqueConstraint(
            "tenant_id", "company_id", "movement_id", "sequence", name="uq_stock_cost_layer_source"
        ),
        Index(
            "ix_stock_cost_layer_fifo", "tenant_id", "company_id", "pool_id", "received_on", "id"
        ),
        Index(
            "ix_stock_cost_layer_remaining",
            "tenant_id",
            "company_id",
            "pool_id",
            "remaining_quantity",
            "id",
        ),
        CheckConstraint(
            "quantity > 0 AND value >= 0 AND remaining_quantity >= 0 AND "
            "remaining_quantity <= quantity AND remaining_value >= 0 AND "
            "remaining_value <= value AND (remaining_quantity > 0 OR remaining_value = 0)",
            name="stock_cost_layer_balance",
        ),
        MARIADB_TABLE_ARGS,
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    received_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    remaining_value: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockCostPoolEvent(StockMoneyRecord):
    __tablename__ = "stock_cost_pool_event"
    __table_args__ = (
        *constraints("stock_cost_pool_event"),
        reference("pool_id", "stock_cost_pool", "fk_stock_pool_event_pool"),
        reference("movement_id", "stock_movement", "fk_stock_pool_event_movement"),
        UniqueConstraint(
            "tenant_id", "company_id", "movement_id", name="uq_stock_pool_event_movement"
        ),
        Index("ix_stock_pool_event_pool", "tenant_id", "company_id", "pool_id", "id"),
        CheckConstraint(
            "before_quantity >= 0 AND after_quantity >= 0 AND "
            "before_value >= 0 AND after_value >= 0",
            name="stock_pool_event_values",
        ),
        CheckConstraint("method IN ('FIFO','MOVING_AVERAGE')", name="stock_pool_event_method"),
        MARIADB_TABLE_ARGS,
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    before_quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    after_quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    before_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    after_value: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockCostAllocation(StockMoneyRecord):
    __tablename__ = "stock_cost_allocation"
    __table_args__ = (
        *constraints("stock_cost_allocation"),
        reference("pool_id", "stock_cost_pool", "fk_stock_cost_allocation_pool"),
        reference("layer_id", "stock_cost_layer", "fk_stock_cost_allocation_layer"),
        reference("movement_id", "stock_movement", "fk_stock_cost_allocation_movement"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "movement_id",
            "layer_key",
            name="uq_stock_cost_allocation_layer",
        ),
        CheckConstraint(
            f"(layer_id IS NULL AND layer_key = {ZERO_KEY}) OR "
            "(layer_id IS NOT NULL AND layer_key = layer_id)",
            name="stock_cost_allocation_key",
        ),
        Index("ix_stock_cost_allocation_movement", "tenant_id", "company_id", "movement_id", "id"),
        CheckConstraint("quantity > 0 AND value >= 0", name="stock_cost_allocation_values"),
        MARIADB_TABLE_ARGS,
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    layer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    layer_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockValueEntry(StockMoneyRecord):
    __tablename__ = "stock_value_entry"
    __table_args__ = (
        *constraints("stock_value_entry"),
        reference("movement_id", "stock_movement", "fk_stock_value_entry_movement"),
        reference("pool_id", "stock_cost_pool", "fk_stock_value_entry_pool"),
        UniqueConstraint(
            "tenant_id", "company_id", "movement_id", name="uq_stock_value_entry_movement"
        ),
        Index("ix_stock_value_entry_pool", "tenant_id", "company_id", "pool_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    pool_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockUnitPosition(Record):
    __tablename__ = "stock_unit_position"
    __table_args__ = (
        *constraints("stock_unit_position"),
        reference("unit_id", "stock_unit", "fk_stock_unit_position_unit"),
        reference("position_id", "stock_position", "fk_stock_unit_position_position"),
        reference("last_movement_id", "stock_movement", "fk_stock_unit_position_movement"),
        reference("origin_id", "stock_receipt_origin", "fk_stock_unit_position_origin"),
        CheckConstraint(
            "position_id IS NULL OR origin_id IS NOT NULL", name="stock_unit_position_origin"
        ),
        UniqueConstraint("tenant_id", "company_id", "unit_id", name="uq_stock_unit_position_unit"),
        Index("ix_stock_unit_position_position", "tenant_id", "company_id", "position_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    last_movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    origin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class StockMovementUnit(StockMoneyRecord):
    __tablename__ = "stock_movement_unit"
    __table_args__ = (
        *constraints("stock_movement_unit"),
        reference("movement_id", "stock_movement", "fk_stock_movement_unit_movement"),
        reference("unit_id", "stock_unit", "fk_stock_movement_unit_unit"),
        reference("origin_id", "stock_receipt_origin", "fk_stock_movement_unit_origin"),
        UniqueConstraint(
            "tenant_id", "company_id", "movement_id", "unit_id", name="uq_stock_movement_unit"
        ),
        Index("ix_stock_movement_unit_unit", "tenant_id", "company_id", "unit_id", "id"),
        CheckConstraint("carrying_value >= 0", name="stock_movement_unit_value"),
        MARIADB_TABLE_ARGS,
    )
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    carrying_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    origin_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class StockSourceClaim(StockMoneyRecord):
    __tablename__ = "stock_source_claim"
    __table_args__ = (
        *constraints("stock_source_claim"),
        reference("movement_id", "stock_movement", "fk_stock_source_claim_movement"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "movement_id",
            "claim_type",
            name="uq_stock_source_claim_type",
        ),
        CheckConstraint("quantity >= 0 AND value >= 0", name="stock_source_claim_values"),
        CheckConstraint(
            "claim_type IN ('RETURN','TRANSFER','INVOICE','REVERSAL')",
            name="stock_source_claim_type",
        ),
        MARIADB_TABLE_ARGS,
    )
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    claim_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="RETURN", server_default="RETURN"
    )
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockOriginClaim(Record):
    __tablename__ = "stock_origin_claim"
    __table_args__ = (
        *constraints("stock_origin_claim"),
        reference("source_movement_id", "stock_movement", "fk_stock_origin_claim_movement"),
        reference("origin_id", "stock_receipt_origin", "fk_stock_origin_claim_origin"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_movement_id",
            "origin_id",
            "claim_type",
            name="uq_stock_origin_claim_identity",
        ),
        CheckConstraint("quantity >= 0", name="stock_origin_claim_quantity"),
        CheckConstraint(
            "claim_type IN ('RETURN','TRANSFER','INVOICE','REVERSAL')",
            name="stock_origin_claim_type",
        ),
        MARIADB_TABLE_ARGS,
    )
    source_movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    origin_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockClaimAllocation(StockMoneyRecord):
    """Immutable claim evidence; counters can be rebuilt and reversals unwind exactly."""

    __tablename__ = "stock_claim_allocation"
    __table_args__ = (
        *constraints("stock_claim_allocation"),
        reference("source_movement_id", "stock_movement", "fk_stock_claim_allocation_source"),
        reference("movement_id", "stock_movement", "fk_stock_claim_allocation_movement"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "movement_id",
            "claim_type",
            name="uq_stock_claim_allocation_move",
        ),
        Index(
            "ix_stock_claim_allocation_source",
            "tenant_id",
            "company_id",
            "source_movement_id",
            "id",
        ),
        CheckConstraint("quantity > 0 AND value >= 0", name="stock_claim_allocation_values"),
        CheckConstraint(
            "claim_type IN ('RETURN','TRANSFER','INVOICE','REVERSAL')",
            name="stock_claim_allocation_type",
        ),
        MARIADB_TABLE_ARGS,
    )
    source_movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)


class StockTransferDestination(Record):
    """Indexed shipment destination, including transfers still held in transit."""

    __tablename__ = "stock_transfer_destination"
    __table_args__ = (
        *constraints("stock_transfer_destination"),
        reference("transit_movement_id", "stock_movement", "fk_stock_transfer_destination_move"),
        reference("destination_position_id", "stock_position", "fk_stock_transfer_destination_pos"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "transit_movement_id",
            name="uq_stock_transfer_destination_move",
        ),
        Index(
            "ix_stock_transfer_destination_target",
            "tenant_id",
            "company_id",
            "destination_position_id",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    transit_movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    destination_position_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class StockOpeningBridge(StockMoneyRecord):
    __tablename__ = "stock_opening_bridge"
    __table_args__ = (
        *constraints("stock_opening_bridge"),
        reference("value_entry_id", "stock_value_entry", "fk_stock_opening_bridge_value"),
        reference("journal_line_id", "journal_line", "fk_stock_opening_bridge_journal_line"),
        UniqueConstraint(
            "tenant_id", "company_id", "value_entry_id", name="uq_stock_opening_bridge_value"
        ),
        Index("ix_stock_opening_bridge_line", "tenant_id", "company_id", "journal_line_id", "id"),
        CheckConstraint("amount > 0", name="stock_opening_bridge_amount"),
        MARIADB_TABLE_ARGS,
    )
    value_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


MODELS = (
    StockPosition,
    StockBalance,
    StockAccountPolicy,
    StockPosting,
    StockExecutionPlan,
    StockCostPool,
    StockMovement,
    StockReceiptOrigin,
    StockOriginBalance,
    StockOriginAllocation,
    StockCostLayer,
    StockCostPoolEvent,
    StockCostAllocation,
    StockValueEntry,
    StockUnitPosition,
    StockMovementUnit,
    StockSourceClaim,
    StockOriginClaim,
    StockClaimAllocation,
    StockTransferDestination,
    StockOpeningBridge,
)

# Explicit FK indexes avoid MySQL adding unmodelled implicit indexes. Reuse an
# existing unique/key prefix when it already covers the complete scoped FK.
for _stock_model in MODELS:
    _stock_table = cast(Table, _stock_model.__table__)
    for _stock_fk in _stock_table.foreign_key_constraints:
        _stock_columns = [element.parent.name for element in _stock_fk.elements]
        _stock_keys = [
            [column.name for column in key.columns]
            for key in (*_stock_table.indexes, *_stock_table.constraints)
            if isinstance(key, Index | UniqueConstraint)
        ]
        if not any(key[: len(_stock_columns)] == _stock_columns for key in _stock_keys):
            Index(
                f"ix_{_stock_table.name}_{_stock_columns[-1]}",
                *(_stock_table.c[key] for key in _stock_columns),
            )

IMMUTABLE = (
    StockExecutionPlan,
    StockPosition,
    StockPosting,
    StockMovement,
    StockReceiptOrigin,
    StockOriginAllocation,
    StockCostPoolEvent,
    StockCostAllocation,
    StockValueEntry,
    StockMovementUnit,
    StockOpeningBridge,
    StockClaimAllocation,
    StockTransferDestination,
)


@event.listens_for(Session, "before_flush")
def protect_stock_history(db: Session, _context: object, _instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, StockMoneyRecord):
            state = inspect(row)
            assert isinstance(state, InstanceState)
            if state.attrs.currency.history.has_changes():
                raise ConflictError("stock carrying-value currency is immutable")
        if isinstance(row, MODELS) and row in db.deleted:
            raise ConflictError("stock evidence and guarded state cannot be deleted")
        if isinstance(row, IMMUTABLE) and db.is_modified(row, include_collections=True):
            raise ConflictError("posted stock evidence is immutable")
        if isinstance(row, StockCostLayer):
            state = inspect(row)
            assert isinstance(state, InstanceState)
            if any(
                state.attrs[key].history.has_changes()
                for key in (
                    "pool_id",
                    "movement_id",
                    "sequence",
                    "received_on",
                    "quantity",
                    "value",
                )
            ):
                raise ConflictError("cost layer origin is immutable")
