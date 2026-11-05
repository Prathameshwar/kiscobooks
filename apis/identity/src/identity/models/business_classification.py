"""Global seeded classifications and tenant-scoped company role bindings.

Reference rows have stable natural keys and no tenant CRUD. Bindings are owned by
the company and changed through its audited create/update routes.
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class ClassificationColumns(Base):
    __abstract__ = True

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BusinessCategory(ClassificationColumns):
    __tablename__ = "business_category"
    __table_args__ = (MARIADB_TABLE_ARGS,)


class BusinessRole(ClassificationColumns):
    __tablename__ = "business_role"
    __table_args__ = (MARIADB_TABLE_ARGS,)


class StoreFormat(ClassificationColumns):
    __tablename__ = "store_format"
    __table_args__ = (MARIADB_TABLE_ARGS,)


class CompanyBusinessRole(IdMixin, TenantMixin, Base):
    __tablename__ = "company_business_role"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "business_role_code", name="uq_company_business_role_binding"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_company_business_role_company",
        ),
        Index("ix_company_business_role_code", "business_role_code"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    business_role_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_role.code", name="fk_company_business_role_code"),
        nullable=False,
    )
