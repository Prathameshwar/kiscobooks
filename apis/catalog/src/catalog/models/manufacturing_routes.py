"""Sequential route definitions; time estimates never schedule work or post costs."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    DECIMAL,
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


class ManufacturingRoute(ClassificationMaster):
    __tablename__ = "manufacturing_route"
    __table_args__ = (*master_constraints("manufacturing_route"), MARIADB_TABLE_ARGS)


class ManufacturingRouteRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "manufacturing_route_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_manufacturing_route_rev_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "route_id",
            "revision",
            name="uq_manufacturing_route_rev_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "route_id"],
            [
                "manufacturing_route.tenant_id",
                "manufacturing_route.company_id",
                "manufacturing_route.id",
            ],
            name="fk_manufacturing_route_rev_parent",
        ),
        Index(
            "ix_manufacturing_route_rev_published",
            "tenant_id",
            "company_id",
            "route_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint(
            "revision >= 1 AND row_version >= 1 AND step_count BETWEEN 0 AND 50",
            name="route_rev_numbers",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','RETIRED') AND "
            "((status = 'DRAFT' AND published_at IS NULL) OR "
            "(status IN ('PUBLISHED','RETIRED') AND published_at IS NOT NULL))",
            name="route_rev_status",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    route_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="DRAFT")
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    specification: Mapped[str] = mapped_column(String(2000), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ManufacturingRouteStep(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "manufacturing_route_step"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_manufacturing_route_step_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "sequence",
            name="uq_manufacturing_route_step_sequence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "manufacturing_route_revision.tenant_id",
                "manufacturing_route_revision.company_id",
                "manufacturing_route_revision.id",
            ],
            name="fk_manufacturing_route_step_parent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "operation_revision_id"],
            [
                "manufacturing_operation_revision.tenant_id",
                "manufacturing_operation_revision.company_id",
                "manufacturing_operation_revision.id",
            ],
            name="fk_manufacturing_route_step_operation",
        ),
        Index(
            "ix_manufacturing_route_step_operation",
            "tenant_id",
            "company_id",
            "operation_revision_id",
        ),
        CheckConstraint("sequence BETWEEN 1 AND 50", name="route_step_sequence"),
        CheckConstraint(
            "setup_minutes >= 0 AND run_minutes >= 0 AND "
            "lead_time_minutes >= 0 AND quantity_basis > 0",
            name="route_step_times",
        ),
        CheckConstraint("time_basis IN ('PER_OUTPUT_UNIT','PER_BATCH')", name="route_step_basis"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    setup_minutes: Mapped[Decimal] = mapped_column(
        DECIMAL(19, 4), nullable=False, default=Decimal("0")
    )
    run_minutes: Mapped[Decimal] = mapped_column(
        DECIMAL(19, 4), nullable=False, default=Decimal("0")
    )
    lead_time_minutes: Mapped[Decimal] = mapped_column(
        DECIMAL(19, 4), nullable=False, default=Decimal("0")
    )
    time_basis: Mapped[str] = mapped_column(String(20), nullable=False, default="PER_OUTPUT_UNIT")
    quantity_basis: Mapped[Decimal] = mapped_column(
        DECIMAL(19, 4), nullable=False, default=Decimal("1")
    )
