"""Explicit company enrollment for the installation's authenticated Catalog source."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import Boolean, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CatalogSourceEnrollment(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "catalog_source_enrollment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", name="uq_catalog_enrollment_company"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_catalog_enrollment_company",
        ),
        Index("ix_catalog_enrollment_discovery", "is_active", "id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
