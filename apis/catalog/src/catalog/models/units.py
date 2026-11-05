"""Catalog-owned unit and packaging masters; never physical stock records."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, Uuid7
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv


class UnitOfMeasure(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    __tablename__ = "unit_of_measure"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_unit_of_measure_scope_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_unit_of_measure_scope_code"),
        Index("ix_unit_of_measure_scope_name_id", "tenant_id", "company_id", "name", "id"),
        Index(
            "ix_unit_of_measure_scope_dimension_code",
            "tenant_id",
            "company_id",
            "dimension",
            "code",
            "id",
        ),
        CheckConstraint("decimal_places >= 0 AND decimal_places <= 4", name="unit_precision"),
        CheckConstraint("quantity_increment > 0", name="unit_increment"),
        CheckConstraint("row_version > 0", name="unit_row_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_increment: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class UnitConversion(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "unit_conversion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "from_unit_id", name="uq_unit_conversion_source"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "from_unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_unit_conversion_source",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "canonical_unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_unit_conversion_canonical",
        ),
        Index("ix_unit_conversion_canonical", "tenant_id", "company_id", "canonical_unit_id"),
        CheckConstraint("numerator > 0 AND denominator > 0", name="unit_conversion_positive"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    from_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    canonical_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    numerator: Mapped[int] = mapped_column(BigInteger, nullable=False)
    denominator: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CompoundUnitComponent(IdMixin, TenantMixin, AuditMixin, Base):
    """One row of a compound unit's multiplicative decomposition.

    A compound unit is defined as the product of its components — ``1 case``
    might be ``12 x bag`` where each ``bag`` is itself ``5 x kg``. Resolution
    (see :func:`catalog.domain.unit_resolution.compound_factor`) multiplies the
    component quantities and follows each child's own conversion.
    """

    __tablename__ = "compound_unit_component"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_compound_unit_component_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "parent_unit_id",
            "ordinal",
            name="uq_compound_unit_component_position",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "parent_unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_compound_unit_component_parent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "child_unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_compound_unit_component_child",
        ),
        CheckConstraint("quantity > 0", name=conv("ck_compound_unit_component_quantity")),
        CheckConstraint("ordinal >= 1", name=conv("ck_compound_unit_component_ordinal")),
        CheckConstraint(
            "parent_unit_id <> child_unit_id", name=conv("ck_compound_unit_component_not_self")
        ),
        CheckConstraint("row_version >= 1", name=conv("ck_compound_unit_component_row_version")),
        Index(
            "ix_compound_unit_component_parent",
            "tenant_id",
            "company_id",
            "parent_unit_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    parent_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    child_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    # SMALLINT, as revision 0154 created it.
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class UnitTaxCode(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "unit_tax_code"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "unit_id",
            "jurisdiction",
            "valid_from",
            name="uq_unit_tax_code_start",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_unit_tax_code_unit",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="unit_tax_code_dates"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(30), nullable=False)
    official_code: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PackType(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    __tablename__ = "pack_type"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_pack_type_scope_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_pack_type_scope_code"),
        Index("ix_pack_type_scope_name_id", "tenant_id", "company_id", "name", "id"),
        CheckConstraint("row_version > 0", name="pack_type_row_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
