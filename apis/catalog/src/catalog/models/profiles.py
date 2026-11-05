"""Native reusable identifier profiles; physical identifiers remain Billing-owned."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints


class IdentifierProfile(ClassificationMaster):
    __tablename__ = "identifier_profile"
    __table_args__ = (
        *master_constraints("identifier_profile"),
        CheckConstraint("normalization_version = 1", name="identifier_profile_normalization"),
        MARIADB_TABLE_ARGS,
    )
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class IdentifierProfileRequirement(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "identifier_profile_requirement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "profile_id",
            "identifier_type",
            name="uq_identifier_requirement_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "profile_id"],
            [
                "identifier_profile.tenant_id",
                "identifier_profile.company_id",
                "identifier_profile.id",
            ],
            name="fk_identifier_requirement_profile",
        ),
        CheckConstraint("identifier_type IN ('SERIAL','IMEI')", name="identifier_requirement_type"),
        CheckConstraint(
            "namespace_rule IN ('COMPANY','MANUFACTURER_SKU')",
            name="identifier_requirement_namespace",
        ),
        CheckConstraint(
            "min_count >= 0 AND max_count >= 1 AND min_count <= max_count AND max_count <= 8",
            name="identifier_requirement_counts",
        ),
        CheckConstraint(
            "requires_slot IN (0,1) AND (max_count <= 1 OR requires_slot = 1)",
            name="identifier_requirement_slots",
        ),
        CheckConstraint(
            "identifier_type != 'IMEI' OR namespace_rule = 'COMPANY'",
            name="identifier_requirement_imei",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(10), nullable=False)
    namespace_rule: Mapped[str] = mapped_column(String(20), nullable=False)
    min_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_slot: Mapped[bool] = mapped_column(Boolean, nullable=False)
