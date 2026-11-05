"""Owner-side source guard and immutable terminal execution evidence."""

import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import JSON, ForeignKeyConstraint, Index, String, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record


class VoucherSourceGuard(Record):
    __tablename__ = "voucher_source_guard"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_source_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "voucher_id", name="uq_voucher_source_identity"
        ),
        MARIADB_TABLE_ARGS,
    )
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    committed_execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class VoucherExecution(Record):
    __tablename__ = "voucher_execution"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_execution_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "execution_id", name="uq_voucher_execution_identity"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "operation_id", name="uq_voucher_operation_identity"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_guard_id"],
            [
                "voucher_source_guard.tenant_id",
                "voucher_source_guard.company_id",
                "voucher_source_guard.id",
            ],
            name="fk_execution_source_guard",
        ),
        Index("ix_voucher_execution_source", "tenant_id", "company_id", "source_guard_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    source_guard_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[Any] = mapped_column(JSON, nullable=False)
    result: Mapped[Any] = mapped_column(JSON, nullable=False)


@event.listens_for(Session, "before_flush")
def immutable_receipts(session: Session, flush_context: object, instances: object) -> None:
    for row in session.dirty:
        if isinstance(row, VoucherExecution) and session.is_modified(row):
            raise ConflictError("owner execution receipts are immutable")
        if isinstance(row, VoucherSourceGuard):
            state = inspect(row)
            assert state is not None
            changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
            if changed & {"tenant_id", "company_id", "voucher_id", "id"}:
                raise ConflictError("owner source identity is immutable")
            history = state.attrs.committed_execution_id.history
            if history.deleted and history.deleted[0] is not None:
                raise ConflictError("committed owner source cannot be released")
    if any(isinstance(row, VoucherExecution | VoucherSourceGuard) for row in session.deleted):
        raise ConflictError("owner execution history cannot be deleted")
