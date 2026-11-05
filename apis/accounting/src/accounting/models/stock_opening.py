"""Opening cutover manifest and immutable per-cohort posting receipts."""

import datetime as dt
import uuid
from typing import Any, Literal

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.stock import StockMoneyRecord, constraints, reference


class StockOpeningControl(StockMoneyRecord):
    __tablename__ = "stock_opening_control"
    __table_args__ = (
        *constraints("stock_opening_control"),
        UniqueConstraint(
            "tenant_id", "company_id", "company_slot", name="uq_stock_opening_company"
        ),
        UniqueConstraint("tenant_id", "company_id", "item_id", name="uq_stock_opening_product"),
        CheckConstraint(
            "(item_id IS NULL AND company_slot IS NOT NULL AND company_slot = 1) OR "
            "(item_id IS NOT NULL AND company_slot IS NULL)",
            name="stock_opening_owner",
        ),
        CheckConstraint("status IN ('OPEN','FINALIZED')", name="stock_opening_status"),
        CheckConstraint("books_begin_date >= '1000-01-01'", name="stock_opening_date"),
        MARIADB_TABLE_ARGS,
    )
    books_begin_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    company_slot: Mapped[int | None] = mapped_column(
        Integer().evaluates_none(), nullable=True, default=1, server_default="1"
    )
    status: Mapped[Literal["OPEN", "FINALIZED"]] = mapped_column(
        String(16), nullable=False, default="OPEN"
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    finalized_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class StockOpeningClaim(StockMoneyRecord):
    __tablename__ = "stock_opening_claim"
    __table_args__ = (
        *constraints("stock_opening_claim"),
        reference("control_id", "stock_opening_control", "fk_stock_opening_claim_control"),
        reference("posting_id", "stock_posting", "fk_stock_opening_claim_posting"),
        reference("movement_id", "stock_movement", "fk_stock_opening_claim_movement"),
        UniqueConstraint(
            "tenant_id", "company_id", "movement_id", name="uq_opening_claim_movement"
        ),
        Index("ix_opening_claim_key", "tenant_id", "company_id", "control_id", "source_key", "id"),
        Index("ix_opening_claim_posting", "tenant_id", "company_id", "posting_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    posting_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    movement_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class StockOpeningRevision(StockMoneyRecord):
    __tablename__ = "stock_opening_revision"
    __table_args__ = (
        *constraints("stock_opening_revision"),
        reference("control_id", "stock_opening_control", "fk_opening_revision_control"),
        UniqueConstraint(
            "tenant_id", "company_id", "control_id", "revision", name="uq_opening_revision_number"
        ),
        MARIADB_TABLE_ARGS,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)


@event.listens_for(Session, "before_flush")
def protect_opening(db: Session, _context: object, _instances: object) -> None:
    for row in db.dirty | db.deleted:
        if (
            isinstance(row, StockOpeningControl | StockOpeningClaim | StockOpeningRevision)
            and row in db.deleted
        ):
            raise ConflictError("opening cutover evidence cannot be deleted")
        if isinstance(row, StockOpeningClaim | StockOpeningRevision) and db.is_modified(
            row, include_collections=True
        ):
            raise ConflictError("opening cohort receipts are immutable")
        if isinstance(row, StockOpeningControl):
            state = inspect(row)
            identity_changed = any(
                state.attrs[key].history.has_changes()
                for key in ("books_begin_date", "currency", "item_id", "company_slot")
            )
            manifest_changed = any(
                state.attrs[key].history.has_changes() for key in ("manifest", "manifest_hash")
            )
            retained = any(
                isinstance(candidate, StockOpeningRevision)
                and candidate.control_id == row.id
                and candidate.manifest == row.manifest
                and candidate.manifest_hash == row.manifest_hash
                and candidate.revision == row.row_version
                for candidate in db.new
            )
            if identity_changed or (manifest_changed and not retained):
                raise ConflictError(
                    "opening manifest identity is immutable; replace only before effects"
                )
