"""Single-level BOM authoring; normalized drafts and immutable published children."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints


def reference(
    name: str, column: str, target: str, *, deferred: bool = False
) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", column],
        [f"{target}.tenant_id", f"{target}.company_id", f"{target}.id"],
        name=name,
        use_alter=deferred,
    )


def scope(table: str) -> tuple[UniqueConstraint, CheckConstraint]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{table}_scope"),
        CheckConstraint("row_version >= 1", name=f"{table}_version"),
    )


class Bom(ClassificationMaster):
    __tablename__ = "bom"
    __table_args__ = (*master_constraints("bom"), MARIADB_TABLE_ARGS)


class BomDefinition(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bom_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    specification: Mapped[str] = mapped_column(String(2000), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    definition_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    route_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    batch_minimum: Mapped[Decimal | None] = mapped_column(DECIMAL(19, 4), nullable=True)
    batch_maximum: Mapped[Decimal | None] = mapped_column(DECIMAL(19, 4), nullable=True)
    batch_multiple: Mapped[Decimal | None] = mapped_column(DECIMAL(19, 4), nullable=True)
    component_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def definition_constraints(table: str) -> tuple[Any, ...]:
    return (
        *scope(table),
        reference(f"fk_{table}_bom", "bom_id", "bom"),
        reference(f"fk_{table}_route", "route_revision_id", "manufacturing_route_revision"),
        CheckConstraint("definition_date >= '1000-01-01'", name=f"{table}_date"),
        CheckConstraint(
            "component_count BETWEEN 0 AND 1000 AND output_count BETWEEN 0 AND 100",
            name=f"{table}_counts",
        ),
        CheckConstraint(
            "(batch_minimum IS NULL OR batch_minimum > 0) AND "
            "(batch_maximum IS NULL OR batch_maximum > 0) AND "
            "(batch_multiple IS NULL OR batch_multiple > 0) AND "
            "(batch_minimum IS NULL OR batch_maximum IS NULL OR batch_minimum <= batch_maximum)",
            name=f"{table}_batch",
        ),
        Index(f"ix_{table}_route", "tenant_id", "company_id", "route_revision_id"),
    )


class BomDraft(BomDefinition):
    __tablename__ = "bom_draft"
    __table_args__ = (
        *definition_constraints("bom_draft"),
        UniqueConstraint(
            "tenant_id", "company_id", "bom_id", "draft_number", name="uq_bom_draft_number"
        ),
        reference(
            "fk_bom_draft_publication", "published_revision_id", "bom_revision", deferred=True
        ),
        CheckConstraint("draft_number >= 1", name="bom_draft_number"),
        CheckConstraint(
            "(status = 'DRAFT' AND published_revision_id IS NULL) OR "
            "(status = 'PUBLISHED' AND published_revision_id IS NOT NULL)",
            name="bom_draft_status",
        ),
        MARIADB_TABLE_ARGS,
    )
    draft_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="DRAFT")
    published_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class BomRevision(BomDefinition):
    __tablename__ = "bom_revision"
    __table_args__ = (
        *definition_constraints("bom_revision"),
        UniqueConstraint(
            "tenant_id", "company_id", "bom_id", "revision", name="uq_bom_revision_number"
        ),
        UniqueConstraint("tenant_id", "company_id", "draft_id", name="uq_bom_revision_draft"),
        reference("fk_bom_revision_draft", "draft_id", "bom_draft"),
        CheckConstraint(
            "revision >= 1 AND policy_generation >= 1 AND source_version >= 1",
            name="bom_revision_numbers",
        ),
        CheckConstraint("status IN ('PUBLISHED','RETIRED')", name="bom_revision_status"),
        CheckConstraint("output_count >= 1", name="bom_revision_outputs"),
        Index(
            "ix_bom_revision_published", "tenant_id", "company_id", "bom_id", "published_at", "id"
        ),
        MARIADB_TABLE_ARGS,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PUBLISHED")
    published_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class BomLine(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


def line_constraints(table: str, maximum: int) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{table}_scope"),
        *(
            UniqueConstraint(
                "tenant_id", "company_id", parent, key, name=f"uq_{table}_{parent}_{key}"
            )
            for parent in ("draft_id", "revision_id")
            for key in ("line_key", "sequence")
        ),
        reference(f"fk_{table}_draft", "draft_id", "bom_draft"),
        reference(f"fk_{table}_revision", "revision_id", "bom_revision"),
        reference(f"fk_{table}_item", "item_id", "item"),
        reference(f"fk_{table}_unit", "unit_revision_id", "item_unit_revision"),
        CheckConstraint(
            "(draft_id IS NOT NULL AND revision_id IS NULL) OR "
            "(draft_id IS NULL AND revision_id IS NOT NULL AND unit_revision_id IS NOT NULL)",
            name=f"{table}_parent",
        ),
        CheckConstraint(f"sequence BETWEEN 1 AND {maximum}", name=f"{table}_sequence"),
        Index(f"ix_{table}_item", "tenant_id", "company_id", "item_id"),
        Index(f"ix_{table}_unit", "tenant_id", "company_id", "unit_revision_id"),
    )


class BomComponent(BomLine):
    __tablename__ = "bom_component"
    __table_args__ = (
        *line_constraints("bom_component", 1000),
        reference("fk_bom_component_step", "route_step_id", "manufacturing_route_step"),
        CheckConstraint(
            "quantity > 0 AND loss_fraction >= 0 AND loss_fraction < 1",
            name="bom_component_quantity",
        ),
        CheckConstraint(
            "basis IN ('GROSS_INPUT','NET_REQUIRED') AND timing IN ('PER_BASIS','PER_RUN')",
            name="bom_component_basis",
        ),
        CheckConstraint("basis = 'NET_REQUIRED' OR loss_fraction = 0", name="bom_component_loss"),
        Index("ix_bom_component_step", "tenant_id", "company_id", "route_step_id"),
        MARIADB_TABLE_ARGS,
    )
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(19, 4), nullable=False)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    loss_fraction: Mapped[Decimal] = mapped_column(DECIMAL(19, 8), nullable=False)
    timing: Mapped[str] = mapped_column(String(12), nullable=False)
    route_step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class BomOutput(BomLine):
    __tablename__ = "bom_output"
    __table_args__ = (
        *line_constraints("bom_output", 100),
        *(
            UniqueConstraint(
                "tenant_id", "company_id", parent, key, name=f"uq_bom_output_{parent}_{key}"
            )
            for parent in ("draft_id", "revision_id")
            for key in ("item_id", "primary_slot")
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "item_id",
            "role",
            name="uq_bom_output_assignment",
        ),
        CheckConstraint(
            "nominal_quantity > 0 AND yield_fraction > 0 AND yield_fraction <= 1",
            name="bom_output_quantity",
        ),
        CheckConstraint(
            "role IN ('PRIMARY','CO_PRODUCT','BY_PRODUCT','SCRAP')", name="bom_output_role"
        ),
        MARIADB_TABLE_ARGS,
    )
    nominal_quantity: Mapped[Decimal] = mapped_column(DECIMAL(19, 4), nullable=False)
    yield_fraction: Mapped[Decimal] = mapped_column(DECIMAL(19, 8), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    primary_slot: Mapped[int | None] = mapped_column(
        Integer,
        Computed("CASE WHEN role = 'PRIMARY' THEN 1 ELSE NULL END", persisted=True),
        nullable=True,
    )


class BomAssignment(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "bom_assignment"
    __table_args__ = (
        *scope("bom_assignment"),
        reference("fk_bom_assignment_revision", "bom_revision_id", "bom_revision"),
        reference("fk_bom_assignment_item", "item_id", "item"),
        reference("fk_bom_assignment_warehouse", "warehouse_id", "warehouse"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "bom_revision_id", "item_id", "output_role"],
            [
                f"bom_output.{key}"
                for key in ("tenant_id", "company_id", "revision_id", "item_id", "role")
            ],
            name="fk_bom_assignment_primary",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "scope_key",
            "valid_from",
            "active_slot",
            name="uq_bom_assignment_start",
        ),
        CheckConstraint("output_role = 'PRIMARY'", name="bom_assignment_output"),
        CheckConstraint(
            "valid_from >= '1000-01-01' AND (valid_to IS NULL OR valid_to >= valid_from)",
            name="bom_assignment_dates",
        ),
        Index(
            "ix_bom_assignment_resolve",
            "tenant_id",
            "company_id",
            "item_id",
            "scope_key",
            "is_active",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    bom_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    output_role: Mapped[str] = mapped_column(String(12), nullable=False, default="PRIMARY")
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    scope_key: Mapped[str] = mapped_column(
        String(32),
        Computed(
            "CASE WHEN warehouse_id IS NULL THEN '*' ELSE HEX(warehouse_id) END", persisted=True
        ),
        nullable=False,
    )
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active_slot: Mapped[int | None] = mapped_column(
        Integer, Computed("CASE WHEN is_active THEN 1 ELSE NULL END", persisted=True), nullable=True
    )
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)


BOM_MODELS = (Bom, BomDraft, BomRevision, BomComponent, BomOutput, BomAssignment)
