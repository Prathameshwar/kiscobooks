"""Reusable warranty definitions; claims and service execution remain external."""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints


class WarrantyPolicy(ClassificationMaster):
    __tablename__ = "warranty_policy"
    __table_args__ = (*master_constraints("warranty_policy"), MARIADB_TABLE_ARGS)


class WarrantyPolicyRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "warranty_policy_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_warranty_policy_rev_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "policy_id", "revision", name="uq_warranty_policy_rev_number"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "policy_id"],
            ["warranty_policy.tenant_id", "warranty_policy.company_id", "warranty_policy.id"],
            name="fk_warranty_policy_rev_parent",
        ),
        Index(
            "ix_warranty_policy_rev_published",
            "tenant_id",
            "company_id",
            "policy_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint("revision >= 1 AND row_version >= 1", name="warranty_policy_rev_version"),
        CheckConstraint(
            "(duration_unit = 'DAYS' AND duration BETWEEN 1 AND 36500) "
            "OR (duration_unit = 'MONTHS' AND duration BETWEEN 1 AND 1200) "
            "OR (duration_unit = 'YEARS' AND duration BETWEEN 1 AND 100)",
            name="warranty_policy_rev_duration",
        ),
        CheckConstraint(
            "start_trigger IN ('SALE','DELIVERY','INSTALLATION')",
            name="warranty_policy_rev_trigger",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(10), nullable=False)
    start_trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    coverage_description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
