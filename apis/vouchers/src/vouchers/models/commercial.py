"""Optional commercial attribution on the shared voucher revision."""

import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from vouchers.models.core import Record


class VoucherAssignment(Record, Base):
    __tablename__ = "voucher_assignment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_assignment_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "role",
            "line_key",
            "principal_id",
            name="uq_voucher_assignment_person",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_assignment_revision",
        ),
        CheckConstraint("share > 0 AND share <= 100", name="voucher_assignment_share"),
        CheckConstraint(
            "role IN ('SELLER','BROKER','COLLECTOR','RETURN_HANDLER','PAYMENT_HANDLER')",
            name="voucher_assignment_role",
        ),
        Index(
            "ix_voucher_assignment_principal_list",
            "tenant_id",
            "company_id",
            "role",
            "principal_id",
            "revision_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    line_key: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    share: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    source_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
