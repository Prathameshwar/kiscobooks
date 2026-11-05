"""Reusable native storage instructions; specialist compliance execution stays external."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, UtcDateTime, Uuid7
from sqlalchemy import (
    Boolean,
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


class HandlingProfile(ClassificationMaster):
    __tablename__ = "handling_profile"
    __table_args__ = (*master_constraints("handling_profile"), MARIADB_TABLE_ARGS)


class HandlingProfileRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "handling_profile_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_handling_profile_rev_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "profile_id",
            "revision",
            name="uq_handling_profile_rev_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "profile_id"],
            ["handling_profile.tenant_id", "handling_profile.company_id", "handling_profile.id"],
            name="fk_handling_profile_rev_parent",
        ),
        Index(
            "ix_handling_profile_rev_published",
            "tenant_id",
            "company_id",
            "profile_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint("revision >= 1 AND row_version >= 1", name="handling_profile_rev_version"),
        CheckConstraint(
            "fragile IN (0,1) AND keep_dry IN (0,1) AND keep_upright IN (0,1)",
            name="handling_profile_rev_flags",
        ),
        CheckConstraint(
            "(temperature_min IS NULL OR temperature_min >= -273.15) AND "
            "(temperature_max IS NULL OR temperature_max >= -273.15)",
            name="handling_profile_rev_absolute_zero",
        ),
        CheckConstraint(
            "temperature_min IS NULL OR temperature_max IS NULL "
            "OR temperature_min <= temperature_max",
            name="handling_profile_rev_order",
        ),
        CheckConstraint(
            "((temperature_min IS NOT NULL OR temperature_max IS NOT NULL) "
            "AND temperature_unit IS NOT NULL AND temperature_unit = 'CELSIUS') "
            "OR (temperature_min IS NULL AND temperature_max IS NULL AND temperature_unit IS NULL)",
            name="handling_profile_rev_unit",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    temperature_min: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    temperature_max: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    temperature_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fragile: Mapped[bool] = mapped_column(Boolean, nullable=False)
    keep_dry: Mapped[bool] = mapped_column(Boolean, nullable=False)
    keep_upright: Mapped[bool] = mapped_column(Boolean, nullable=False)
    instructions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
