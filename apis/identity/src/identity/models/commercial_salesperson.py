"""Company-approved commercial representative; no login or payroll implication."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import Boolean, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CommercialSalesperson(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "commercial_salesperson"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "code"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_commercial_salesperson_company",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user.tenant_id", "user.id"],
            name="fk_commercial_salesperson_user",
        ),
        Index("ix_commercial_salesperson_tenant_user", "tenant_id", "user_id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
