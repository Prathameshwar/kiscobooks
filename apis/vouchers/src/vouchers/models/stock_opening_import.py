"""Durable opening import metadata; effects remain ordinary native vouchers."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from vouchers.models.core import Record


class StockOpeningImport(Record, Base):
    __tablename__ = "stock_opening_import"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_stock_opening_import_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "source_key", name="uq_stock_opening_import_source"
        ),
        UniqueConstraint("tenant_id", "company_id", "input_hash", name="uq_opening_import_input"),
        CheckConstraint(
            "state IN ('STAGED','VALIDATING','READY','COMMITTING',"
            "'DRAFTS_CREATED','BLOCKED','CANCELLED')",
            name="opening_import_state",
        ),
        CheckConstraint("row_version > 0", name="opening_import_version"),
        Index("ix_stock_opening_import_page", "tenant_id", "company_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="STAGED")
    review: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    effects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    reviewed_authority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class StockOpeningImportClaim(Record, Base):
    __tablename__ = "stock_opening_import_claim"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_opening_import_claim_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "control_id",
            "source_key",
            "voucher_id",
            name="uq_opening_import_cohort",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "job_id"],
            [
                "stock_opening_import.tenant_id",
                "stock_opening_import.company_id",
                "stock_opening_import.id",
            ],
            name="fk_opening_import_claim_job",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_opening_import_claim_voucher",
        ),
        Index("ix_opening_import_claim_job", "tenant_id", "company_id", "job_id", "id"),
        Index("ix_opening_import_claim_voucher", "tenant_id", "company_id", "voucher_id", "id"),
        CheckConstraint("row_version > 0", name="opening_import_claim_version"),
        MARIADB_TABLE_ARGS,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


@event.listens_for(Session, "before_flush")
def protect_import(db: Session, _context: object, _instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, StockOpeningImportClaim) and (row in db.deleted or db.is_modified(row)):
            raise ConflictError("opening import cohort effects are immutable")
        if isinstance(row, StockOpeningImport):
            if row in db.deleted:
                raise ConflictError("opening import evidence cannot be deleted")
            state = inspect(row)
            if any(
                state.attrs[key].history.has_changes()
                for key in ("payload", "input_hash", "source_key")
            ):
                raise ConflictError(
                    "opening import source is immutable; stage a corrected source revision"
                )
