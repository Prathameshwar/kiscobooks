"""Company-approved transaction currencies; base currency is always implicit."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import CHAR, Boolean, ForeignKeyConstraint, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanyCurrencyAllowance(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "company_currency_allowance"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "currency_code"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_company_currency_allowance_company",
        ),
        ForeignKeyConstraint(
            ["currency_code"],
            ["currency.code"],
            name="fk_company_currency_allowance_currency",
        ),
        Index(
            "ix_company_currency_allowance_company_active", "tenant_id", "company_id", "is_active"
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
