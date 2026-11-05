"""Reusable operation definitions; no machines, schedules or execution records."""

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


class ManufacturingOperation(ClassificationMaster):
    __tablename__ = "manufacturing_operation"
    __table_args__ = (*master_constraints("manufacturing_operation"), MARIADB_TABLE_ARGS)


class ManufacturingOperationRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "manufacturing_operation_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_manufacturing_op_rev_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "operation_id",
            "revision",
            name="uq_manufacturing_op_rev_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "operation_id"],
            [
                "manufacturing_operation.tenant_id",
                "manufacturing_operation.company_id",
                "manufacturing_operation.id",
            ],
            name="fk_manufacturing_op_rev_parent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "service_item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_manufacturing_op_rev_service",
        ),
        Index(
            "ix_manufacturing_op_rev_published",
            "tenant_id",
            "company_id",
            "operation_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint("revision >= 1 AND row_version >= 1", name="manufacturing_op_rev_version"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','RETIRED') AND "
            "((status = 'DRAFT' AND published_at IS NULL) OR "
            "(status IN ('PUBLISHED','RETIRED') AND published_at IS NOT NULL))",
            name="manufacturing_op_rev_status",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="DRAFT")
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    specification: Mapped[str] = mapped_column(String(2000), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    service_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
