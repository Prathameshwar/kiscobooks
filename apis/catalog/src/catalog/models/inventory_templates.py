"""Versioned inventory requirements; no physical stock or valuation balances."""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
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


class InventoryProfileTemplate(ClassificationMaster):
    __tablename__ = "inventory_profile_template"
    __table_args__ = (*master_constraints("inventory_profile_template"), MARIADB_TABLE_ARGS)


class InventoryProfileTemplateRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "inventory_profile_template_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_inventory_template_rev_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "template_id",
            "revision",
            name="uq_inventory_template_rev_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "template_id"],
            [
                "inventory_profile_template.tenant_id",
                "inventory_profile_template.company_id",
                "inventory_profile_template.id",
            ],
            name="fk_inventory_template_rev_parent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "identifier_profile_id"],
            [
                "identifier_profile.tenant_id",
                "identifier_profile.company_id",
                "identifier_profile.id",
            ],
            name="fk_inventory_template_rev_identifier",
        ),
        Index(
            "ix_inventory_template_rev_identifier",
            "tenant_id",
            "company_id",
            "identifier_profile_id",
        ),
        Index(
            "ix_inventory_template_rev_published",
            "tenant_id",
            "company_id",
            "template_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint(
            "revision >= 1 AND row_version >= 1", name="inventory_template_rev_version"
        ),
        CheckConstraint(
            "lot_tracking IN (0,1) AND serial_tracking IN (0,1) "
            "AND expiry_required IN (0,1) AND manufacture_date_required IN (0,1)",
            name="inventory_template_rev_flags",
        ),
        CheckConstraint("issue_strategy IN ('FIFO','FEFO')", name="inventory_template_rev_issue"),
        CheckConstraint(
            "valuation_method IN ('FIFO','MOVING_AVERAGE','SPECIFIC')",
            name="inventory_template_rev_valuation",
        ),
        CheckConstraint(
            "shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 36500",
            name="inventory_template_rev_shelf",
        ),
        CheckConstraint(
            "minimum_remaining_life_days IS NULL "
            "OR minimum_remaining_life_days BETWEEN 0 AND 36500",
            name="inventory_template_rev_remaining",
        ),
        CheckConstraint(
            "lot_tracking = 1 OR (expiry_required = 0 AND manufacture_date_required = 0 "
            "AND shelf_life_days IS NULL AND minimum_remaining_life_days IS NULL)",
            name="inventory_template_rev_dates",
        ),
        CheckConstraint(
            "expiry_required = 1 "
            "OR (issue_strategy != 'FEFO' AND minimum_remaining_life_days IS NULL)",
            name="inventory_template_rev_expiry",
        ),
        CheckConstraint(
            "shelf_life_days IS NULL OR minimum_remaining_life_days IS NULL "
            "OR minimum_remaining_life_days <= shelf_life_days",
            name="inventory_template_rev_life",
        ),
        CheckConstraint(
            "serial_tracking = 1 "
            "OR (identifier_profile_id IS NULL AND valuation_method != 'SPECIFIC')",
            name="inventory_template_rev_serial",
        ),
        CheckConstraint(
            "negative_stock_policy IN ('BLOCK','WARN','ALLOW')",
            name="negative_stock",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    identifier_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lot_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    serial_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expiry_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manufacture_date_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_remaining_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_strategy: Mapped[str] = mapped_column(String(10), nullable=False)
    valuation_method: Mapped[str] = mapped_column(String(20), nullable=False)
    negative_stock_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default="BLOCK", server_default="BLOCK"
    )
