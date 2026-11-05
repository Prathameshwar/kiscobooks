"""Short owner leases freeze stock definitions while Accounting commits effects."""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, Session, SessionTransaction, mapped_column

from catalog.models.classification import CatalogPolicyState

RETIREMENT_CHECKS = "catalog_native_stock_retirement_checks"
RETIREMENT_COMMAND = "catalog_stock_retirement_command_hash"


@dataclass(frozen=True)
class RetirementClearance:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    table_name: Literal["warehouse", "warehouse_bin"]
    object_id: uuid.UUID
    expected_version: int
    check_id: uuid.UUID
    checked_at: dt.datetime
    expires_at: dt.datetime


def current_clearance(db: Session, check: RetirementClearance) -> bool:
    from billing_platform.db.types import utcnow

    return utcnow() < check.expires_at


class StockSourceFence(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "stock_source_fence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "execution_id", name="uq_stock_source_fence_execution"
        ),
        Index(
            "ix_stock_source_fence_live", "tenant_id", "company_id", "closed_at", "expires_at", "id"
        ),
        CheckConstraint("expires_at > created_at", name="stock_source_fence_lifetime"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


# All ORM authoring paths, including bulk commands and future callers, share the
# same company lock. A source identity cannot change during a live owner lease.
PROTECTED = frozenset(
    {
        "item",
        "product_family",
        "item_inventory_profile",
        "inventory_profile_template_revision",
        "inventory_profile_template",
        "unit_of_measure",
        "item_unit_binding",
        "item_unit_revision",
        "warehouse",
        "warehouse_bin",
        "warehouse_operation_policy_revision",
        "company_warehouse_configuration",
        "item_warehouse_policy",
        "item_warehouse_permission",
        "product_type_revision",
        "identifier_profile",
        "identifier_profile_requirement",
        "item_group",
        "item_group_parent",
        "family_group_assignment",
    }
)


@event.listens_for(Session, "before_flush")
def protect_stock_sources(db: Session, _context: object, _instances: object) -> None:
    from billing_platform.db.types import utcnow

    scopes: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for row in db.new | db.dirty | db.deleted:
        if isinstance(row, StockSourceFence):
            if row in db.deleted:
                raise ConflictError("stock source evidence cannot be deleted")
            if row in db.dirty:
                state = inspect(row)
                if any(
                    state.attrs[key].history.has_changes()
                    for key in (
                        "tenant_id",
                        "company_id",
                        "execution_id",
                        "actor_user_id",
                        "request_hash",
                        "expires_at",
                        "facts",
                        "created_by",
                        "created_at",
                    )
                ) or (
                    state.attrs.closed_at.history.deleted
                    and state.attrs.closed_at.history.deleted[0] is not None
                ):
                    raise ConflictError("stock source evidence is immutable")
        elif getattr(row, "__tablename__", "") in PROTECTED:
            if row in db.dirty and not db.is_modified(row, include_collections=True):
                continue
            scopes.add((row.tenant_id, row.company_id))
            if getattr(row, "__tablename__", "") in {"warehouse", "warehouse_bin"}:
                state = inspect(row)
                if row in db.deleted:
                    raise ConflictError("stock locations must be retired, never deleted")
                if (
                    row in db.dirty
                    and state.attrs.is_active.history.has_changes()
                    and row.is_active is False
                ):
                    check = db.info.get(RETIREMENT_CHECKS, {}).get((row.__tablename__, row.id))
                    if (
                        not isinstance(check, RetirementClearance)
                        or not current_clearance(db, check)
                        or (check.tenant_id, check.company_id) != (row.tenant_id, row.company_id)
                        or row.row_version
                        not in {check.expected_version, check.expected_version + 1}
                    ):
                        raise ConflictError(
                            "a current coordinated NoStock check is required "
                            "to retire this location"
                        )
    for tenant, company in sorted(scopes):
        db.scalar(
            select(CatalogPolicyState)
            .where(
                CatalogPolicyState.tenant_id == tenant,
                CatalogPolicyState.company_id == company,
            )
            .with_for_update()
        )
        if db.scalar(
            select(StockSourceFence.id)
            .where(
                StockSourceFence.tenant_id == tenant,
                StockSourceFence.company_id == company,
                StockSourceFence.closed_at.is_(None),
                StockSourceFence.expires_at > utcnow(),
            )
            .limit(1)
        ):
            raise ConflictError(
                "stock posting is using these definitions; retry after it completes"
            )


@event.listens_for(Session, "before_commit")
def finish_retirement(db: Session) -> None:
    if db.in_nested_transaction():
        return
    checks = db.info.get(RETIREMENT_CHECKS, {})
    if not checks:
        return
    if any(not current_clearance(db, check) for check in checks.values()):
        raise ConflictError("stock retirement clearance expired; retry the unchanged command")
    db.flush()
    from catalog.models.warehouses import Warehouse, WarehouseBin

    for check in checks.values():
        model = Warehouse if check.table_name == "warehouse" else WarehouseBin
        row = db.execute(
            select(model.is_active, model.row_version).where(
                model.tenant_id == check.tenant_id,
                model.company_id == check.company_id,
                model.id == check.object_id,
            )
        ).first()
        if (
            not current_clearance(db, check)
            or row is None
            or row.is_active
            or row.row_version not in {check.expected_version, check.expected_version + 1}
        ):
            raise ConflictError("stock retirement changed after its coordinated check")


@event.listens_for(Session, "after_transaction_end")
def clear_retirement(db: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        db.info.pop(RETIREMENT_CHECKS, None)
        db.info.pop(RETIREMENT_COMMAND, None)
