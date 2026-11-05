"""Accounting-owned prepared tracking identities, not stock balances or movements."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Quantity, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import InstanceState, Mapped, Session, mapped_column

from accounting.models.masters import Record


def identity_constraints(name: str) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        Index(f"ix_{name}_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name=f"{name}_version"),
    )


class StockLot(Record):
    __tablename__ = "stock_lot"
    __table_args__ = (
        *identity_constraints("stock_lot"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "namespace_key",
            "normalized_code",
            name="uq_stock_lot_identity",
        ),
        Index("ix_stock_lot_code", "tenant_id", "company_id", "normalized_code", "id"),
        Index("ix_stock_lot_expiry", "tenant_id", "company_id", "expires_on", "id"),
        Index("ix_stock_lot_item", "tenant_id", "company_id", "item_id", "id"),
        Index("ix_stock_lot_source_party", "tenant_id", "company_id", "source_party_id", "id"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="stock_lot_status"),
        CheckConstraint(
            "(mrp_amount IS NULL AND mrp_currency IS NULL AND mrp_unit_id IS NULL) OR "
            "(mrp_amount > 0 AND mrp_currency IS NOT NULL AND mrp_unit_id IS NOT NULL)",
            name="stock_lot_mrp",
        ),
        CheckConstraint(
            "expires_on IS NULL OR manufactured_on IS NULL OR expires_on >= manufactured_on",
            name="stock_lot_dates",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_stock_lot_source_party",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_code: Mapped[str] = mapped_column(
        String(100).with_variant(String(100, collation="utf8mb4_bin"), "mysql", "mariadb"),
        nullable=False,
    )
    namespace_key: Mapped[str] = mapped_column(String(40), nullable=False)
    source_party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    manufactured_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    mrp_amount: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    mrp_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    mrp_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_held: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class StockUnit(Record):
    __tablename__ = "stock_unit"
    __table_args__ = (
        *identity_constraints("stock_unit"),
        Index("ix_stock_unit_item", "tenant_id", "company_id", "item_id", "id"),
        Index("ix_stock_unit_lot", "tenant_id", "company_id", "lot_id", "id"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="stock_unit_status"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "lot_id"],
            ["stock_lot.tenant_id", "stock_lot.company_id", "stock_lot.id"],
            name="fk_stock_unit_lot",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_held: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class StockUnitIdentifier(Record):
    __tablename__ = "stock_unit_identifier"
    __table_args__ = (
        *identity_constraints("stock_unit_identifier"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "identifier_type",
            "namespace_key",
            "normalized_value",
            name="uq_stock_unit_identifier_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "unit_id",
            "identifier_type",
            "slot",
            name="uq_stock_unit_identifier_slot",
        ),
        Index(
            "ix_stock_unit_identifier_lookup", "tenant_id", "company_id", "normalized_value", "id"
        ),
        CheckConstraint("identifier_type IN ('SERIAL','IMEI')", name="stock_unit_identifier_type"),
        CheckConstraint(
            "slot BETWEEN 1 AND 8 AND normalization_version = 1",
            name="stock_unit_identifier_bounds",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_id"],
            ["stock_unit.tenant_id", "stock_unit.company_id", "stock_unit.id"],
            name="fk_stock_unit_identifier_unit",
        ),
        MARIADB_TABLE_ARGS,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(10), nullable=False)
    namespace_key: Mapped[str] = mapped_column(String(40), nullable=False)
    slot: Mapped[int] = mapped_column(nullable=False)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_value: Mapped[str] = mapped_column(
        String(120).with_variant(String(120, collation="utf8mb4_bin"), "mysql", "mariadb"),
        nullable=False,
    )
    normalization_version: Mapped[int] = mapped_column(nullable=False)


class StockTrackingEvent(Record):
    __tablename__ = "stock_tracking_event"
    __table_args__ = (
        *identity_constraints("stock_tracking_event"),
        Index("ix_stock_tracking_event_target", "tenant_id", "company_id", "target_id", "id"),
        CheckConstraint("resource IN ('BATCH','SERIAL')", name="stock_tracking_event_resource"),
        CheckConstraint(
            "action IN ('PREPARE','CORRECT','HOLD','RELEASE','RETIRE','REACTIVATE')",
            name="stock_tracking_event_action",
        ),
        MARIADB_TABLE_ARGS,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    resource: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


MODELS = (StockLot, StockUnit, StockUnitIdentifier, StockTrackingEvent)


@event.listens_for(Session, "before_flush")
def preserve_tracking_identity(db: Session, context: object, instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, StockTrackingEvent | StockUnitIdentifier):
            if row in db.deleted or db.is_modified(row):
                raise ConflictError("tracking history and identifier identities are immutable")
        if isinstance(row, StockLot | StockUnit):
            if row in db.deleted:
                raise ConflictError("tracking registrations must be retired, never deleted")
            fixed = {"item_id", "source_facts"}
            if isinstance(row, StockLot):
                fixed |= {
                    "code",
                    "normalized_code",
                    "namespace_key",
                    "source_party_id",
                    "mrp_amount",
                    "mrp_currency",
                    "mrp_unit_id",
                }
            else:
                fixed.add("lot_id")
            state = inspect(row)
            assert isinstance(state, InstanceState)
            if any(state.attrs[key].history.has_changes() for key in fixed):
                raise ConflictError("tracking identity and original source evidence are immutable")
