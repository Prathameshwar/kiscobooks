"""Native attribute definitions, typed choices and reusable immutable templates."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, UtcDateTime, Uuid7
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints


class AttributeDefinition(ClassificationMaster):
    __tablename__ = "attribute_definition"
    __table_args__ = (
        *master_constraints("attribute_definition"),
        UniqueConstraint(
            "tenant_id", "company_id", "id", "value_type", name="uq_attribute_definition_type"
        ),
        CheckConstraint(
            "value_type IN ('TEXT','INTEGER','DECIMAL','BOOLEAN','DATE')",
            name="attribute_definition_type",
        ),
        CheckConstraint(
            "measurement_dimension IS NULL OR (value_type IN ('INTEGER','DECIMAL') "
            "AND measurement_dimension IN "
            "('COUNT','MASS','VOLUME','LENGTH','AREA','TIME','JOB'))",
            name="attribute_definition_dimension",
        ),
        CheckConstraint("is_variant_capable IN (0,1)", name="attribute_definition_variant"),
        MARIADB_TABLE_ARGS,
    )
    value_type: Mapped[str] = mapped_column(String(10), nullable=False)
    measurement_dimension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_variant_capable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AttributeOption(ClassificationMaster):
    __tablename__ = "attribute_option"
    __table_args__ = (
        *master_constraints("attribute_option", "definition_id"),
        UniqueConstraint(
            "tenant_id", "company_id", "definition_id", "id", name="uq_attribute_option_parent_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "definition_id",
            "value_hash",
            name="uq_attribute_option_value",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id", "value_type"],
            [
                "attribute_definition.tenant_id",
                "attribute_definition.company_id",
                "attribute_definition.id",
                "attribute_definition.value_type",
            ],
            name="fk_attribute_option_definition",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_attribute_option_unit",
        ),
        Index("ix_attribute_option_unit", "tenant_id", "company_id", "unit_id"),
        Index(
            "ix_attribute_option_definition_type",
            "tenant_id",
            "company_id",
            "definition_id",
            "value_type",
        ),
        Index(
            "ix_attribute_option_parent_name",
            "tenant_id",
            "company_id",
            "definition_id",
            "name",
            "id",
        ),
        Index("ix_attribute_option_code", "tenant_id", "company_id", "code", "id"),
        CheckConstraint(
            "(value_type='TEXT' AND value_text IS NOT NULL AND value_integer IS NULL "
            "AND value_decimal IS NULL AND value_boolean IS NULL AND value_date IS "
            "NULL AND unit_id IS NULL) OR "
            "(value_type='INTEGER' AND value_text IS NULL AND value_integer IS NOT "
            "NULL AND value_decimal IS NULL AND value_boolean IS NULL AND value_date "
            "IS NULL) OR "
            "(value_type='DECIMAL' AND value_text IS NULL AND value_integer IS NULL "
            "AND value_decimal IS NOT NULL AND value_boolean IS NULL AND value_date "
            "IS NULL) OR "
            "(value_type='BOOLEAN' AND value_text IS NULL AND value_integer IS NULL "
            "AND value_decimal IS NULL AND value_boolean IS NOT NULL AND value_date "
            "IS NULL AND unit_id IS NULL) OR "
            "(value_type='DATE' AND value_text IS NULL AND value_integer IS NULL AND "
            "value_decimal IS NULL AND value_boolean IS NULL AND value_date IS NOT "
            "NULL AND unit_id IS NULL)",
            name="attribute_option_representation",
        ),
        CheckConstraint(
            "value_boolean IS NULL OR value_boolean IN (0,1)", name="attribute_option_boolean"
        ),
        CheckConstraint(
            "value_date IS NULL OR value_date >= '1000-01-01'", name="attribute_option_date"
        ),
        MARIADB_TABLE_ARGS,
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    value_type: Mapped[str] = mapped_column(String(10), nullable=False)
    value_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value_integer: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value_decimal: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    value_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(mysql.BINARY(32), "mysql"), nullable=False
    )
    canonical_value: Mapped[bytes] = mapped_column(
        LargeBinary(1024).with_variant(mysql.VARBINARY(1024), "mysql"), nullable=False
    )


class AttributeSet(ClassificationMaster):
    __tablename__ = "attribute_set"
    __table_args__ = (*master_constraints("attribute_set"), MARIADB_TABLE_ARGS)


class AttributeSetRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "attribute_set_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_attribute_set_revision_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "attribute_set_id",
            "revision",
            name="uq_attribute_set_revision_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "attribute_set_id"],
            ["attribute_set.tenant_id", "attribute_set.company_id", "attribute_set.id"],
            name="fk_attribute_set_revision_parent",
        ),
        Index(
            "ix_attribute_set_revision_published",
            "tenant_id",
            "company_id",
            "attribute_set_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint(
            "revision >= 1 AND row_version >= 1", name="attribute_set_revision_version"
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attribute_set_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class AttributeSetMember(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "attribute_set_member"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "definition_id",
            name="uq_attribute_set_member_definition",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "position",
            name="uq_attribute_set_member_position",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "attribute_set_revision.tenant_id",
                "attribute_set_revision.company_id",
                "attribute_set_revision.id",
            ],
            name="fk_attribute_set_member_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id"],
            [
                "attribute_definition.tenant_id",
                "attribute_definition.company_id",
                "attribute_definition.id",
            ],
            name="fk_attribute_set_member_definition",
        ),
        Index("ix_attribute_set_member_definition", "tenant_id", "company_id", "definition_id"),
        CheckConstraint("position >= 0 AND position < 128", name="attribute_set_member_position"),
        CheckConstraint(
            "is_required IN (0,1) AND allow_variant_axis IN (0,1)",
            name="attribute_set_member_flags",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_variant_axis: Mapped[bool] = mapped_column(Boolean, nullable=False)
