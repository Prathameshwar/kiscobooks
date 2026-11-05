"""Bounded coordinated retirement leases, sharing the common company guard."""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from vouchers.models.core import Record, VoucherCompanyGuard, VoucherOperation
from vouchers.models.stock import VoucherStockContext


class StockRetirementFence(Record, Base):
    __tablename__ = "stock_retirement_fence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_stock_retirement_scope"),
        UniqueConstraint("tenant_id", "company_id", "check_id", name="uq_stock_retirement_check"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["voucher_company_guard.tenant_id", "voucher_company_guard.company_id"],
            name="fk_stock_retirement_company",
        ),
        Index(
            "ix_stock_retirement_live", "tenant_id", "company_id", "closed_at", "expires_at", "id"
        ),
        CheckConstraint(
            "row_version > 0 AND expires_at > created_at", name="stock_retirement_lifetime"
        ),
        MARIADB_TABLE_ARGS,
    )
    check_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


@event.listens_for(Session, "before_flush")
def guard_retirement(db: Session, _context: object, _instances: object) -> None:
    scopes = {
        (row.tenant_id, row.company_id)
        for row in db.new
        if isinstance(row, VoucherStockContext)
        or (
            isinstance(row, VoucherOperation)
            and isinstance(row.command, dict)
            and isinstance(row.command.get("source_payload"), dict)
            and row.command["source_payload"].get("stock") is not None
        )
    }
    for tenant, company in sorted(scopes):
        db.scalar(
            select(VoucherCompanyGuard)
            .where(
                VoucherCompanyGuard.tenant_id == tenant,
                VoucherCompanyGuard.company_id == company,
            )
            .with_for_update()
        )
        if db.scalar(
            select(StockRetirementFence.id)
            .where(
                StockRetirementFence.tenant_id == tenant,
                StockRetirementFence.company_id == company,
                StockRetirementFence.closed_at.is_(None),
                StockRetirementFence.expires_at > utcnow(),
            )
            .limit(1)
        ):
            raise ConflictError(
                "a warehouse retirement check is in progress; retry after it completes"
            )
    for row in db.dirty | db.deleted:
        if not isinstance(row, StockRetirementFence):
            continue
        if row in db.deleted:
            raise ConflictError("stock retirement evidence cannot be deleted")
        state = inspect(row)
        if any(
            state.attrs[key].history.has_changes()
            for key in (
                "tenant_id",
                "company_id",
                "check_id",
                "actor_user_id",
                "warehouse_id",
                "bin_id",
                "request_hash",
                "expires_at",
                "created_at",
                "created_by",
            )
        ) or (
            state.attrs.closed_at.history.deleted
            and state.attrs.closed_at.history.deleted[0] is not None
        ):
            raise ConflictError("stock retirement evidence is immutable")
