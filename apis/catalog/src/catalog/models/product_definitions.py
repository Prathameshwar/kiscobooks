"""Native product assignments, SKU structure, unit history and pinned configuration."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, Uuid7
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
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column


class ProductDefinitionRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FamilyGroupAssignment(ProductDefinitionRow):
    __tablename__ = "family_group_assignment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p71_0"),
        UniqueConstraint("tenant_id", "company_id", "family_id", "valid_from", name="uq_p71_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_p71_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["item_group.tenant_id", "item_group.company_id", "item_group.id"],
            name="fk_p71_1",
        ),
        CheckConstraint("row_version >= 1", name="p71_check_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="p71_check_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="p71_check_2"),
        Index("ix_p71_0", "tenant_id", "company_id", "family_id", "valid_from", "id"),
        Index("ix_p71_1", "tenant_id", "company_id", "group_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class FamilyCategory(ProductDefinitionRow):
    __tablename__ = "family_category"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p72_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "family_id",
            "category_id",
            "valid_from",
            name="uq_p72_dated_category",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "family_id",
            "scheme_id",
            "primary_slot",
            "valid_from",
            name="uq_p72_dated_primary",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_p72_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scheme_id"],
            ["category_scheme.tenant_id", "category_scheme.company_id", "category_scheme.id"],
            name="fk_p72_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scheme_id", "category_id"],
            [
                "item_category.tenant_id",
                "item_category.company_id",
                "item_category.scheme_id",
                "item_category.id",
            ],
            name="fk_p72_2",
        ),
        CheckConstraint("row_version >= 1", name="p72_check_0"),
        CheckConstraint(
            "(is_primary = 1 AND primary_slot IS NOT NULL AND primary_slot = 1) "
            "OR (is_primary = 0 AND primary_slot IS NULL)",
            name="p72_check_1",
        ),
        CheckConstraint("valid_from >= '1000-01-01'", name="p72_date_floor"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="p72_dates"),
        Index(
            "ix_p72_asof", "tenant_id", "company_id", "family_id", "valid_from", "valid_to", "id"
        ),
        Index("ix_p72_scheme", "tenant_id", "company_id", "scheme_id", "valid_to", "id"),
        Index("ix_p72_0", "tenant_id", "company_id", "family_id", "id"),
        Index("ix_p72_1", "tenant_id", "company_id", "category_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scheme_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False)
    primary_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(
        Date, nullable=False, default=dt.date(1000, 1, 1), server_default=text("'1000-01-01'")
    )
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class FamilyManufacturer(ProductDefinitionRow):
    __tablename__ = "family_manufacturer"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p73_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "family_id",
            "manufacturer_id",
            "production_role",
            "valid_from",
            name="uq_p73_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_p73_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "manufacturer_id"],
            ["manufacturer.tenant_id", "manufacturer.company_id", "manufacturer.id"],
            name="fk_p73_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "manufacturer_id", "site_id"],
            [
                "manufacturer_site.tenant_id",
                "manufacturer_site.company_id",
                "manufacturer_site.manufacturer_id",
                "manufacturer_site.id",
            ],
            name="fk_p73_2",
        ),
        CheckConstraint("row_version >= 1", name="p73_check_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="p73_check_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="p73_check_2"),
        CheckConstraint(
            "production_role IN ('MANUFACTURER','ASSEMBLER','IMPORTER')",
            name="p73_check_3",
        ),
        Index("ix_p73_0", "tenant_id", "company_id", "family_id", "id"),
        Index("ix_p73_1", "tenant_id", "company_id", "manufacturer_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    production_role: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class FamilyAttribute(ProductDefinitionRow):
    __tablename__ = "family_attribute"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p74_0"),
        UniqueConstraint("tenant_id", "company_id", "family_id", "definition_id", name="uq_p74_1"),
        UniqueConstraint("tenant_id", "company_id", "family_id", "position", name="uq_p74_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_p74_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id"],
            [
                "attribute_definition.tenant_id",
                "attribute_definition.company_id",
                "attribute_definition.id",
            ],
            name="fk_p74_1",
        ),
        CheckConstraint("row_version >= 1", name="p74_check_0"),
        CheckConstraint("position BETWEEN 0 AND 127", name="p74_check_1"),
        CheckConstraint("is_axis = 0 OR is_required = 1", name="p74_check_2"),
        Index("ix_p74_0", "tenant_id", "company_id", "family_id", "id"),
        Index("ix_p74_1", "tenant_id", "company_id", "definition_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    is_axis: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class FamilyAttributeOption(ProductDefinitionRow):
    __tablename__ = "family_attribute_option"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p75_0"),
        UniqueConstraint(
            "tenant_id", "company_id", "family_id", "definition_id", "option_id", name="uq_p75_1"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id", "definition_id"],
            [
                "family_attribute.tenant_id",
                "family_attribute.company_id",
                "family_attribute.family_id",
                "family_attribute.definition_id",
            ],
            name="fk_p75_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id", "option_id"],
            [
                "attribute_option.tenant_id",
                "attribute_option.company_id",
                "attribute_option.definition_id",
                "attribute_option.id",
            ],
            name="fk_p75_1",
        ),
        CheckConstraint("row_version >= 1", name="p75_check_0"),
        Index("ix_p75_0", "tenant_id", "company_id", "family_id", "id"),
        Index("ix_p75_1", "tenant_id", "company_id", "option_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    option_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class ItemAttributeValue(ProductDefinitionRow):
    __tablename__ = "item_attribute_value"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p76_0"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "definition_id", name="uq_p76_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_p76_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id"],
            [
                "attribute_definition.tenant_id",
                "attribute_definition.company_id",
                "attribute_definition.id",
            ],
            name="fk_p76_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id", "option_id"],
            [
                "attribute_option.tenant_id",
                "attribute_option.company_id",
                "attribute_option.definition_id",
                "attribute_option.id",
            ],
            name="fk_p76_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_p76_3",
        ),
        CheckConstraint("row_version >= 1", name="p76_check_0"),
        CheckConstraint(
            "value_type IN ('TEXT','INTEGER','DECIMAL','BOOLEAN','DATE')",
            name="p76_check_1",
        ),
        CheckConstraint(
            "(option_id IS NOT NULL AND value_text IS NULL AND value_integer IS NULL AND "
            "value_decimal IS NULL AND value_boolean IS NULL AND value_date IS NULL AND "
            "unit_id IS NULL) OR (option_id IS NULL AND ((value_text IS NOT NULL) + "
            "(value_integer IS NOT NULL) + (value_decimal IS NOT NULL) + (value_boolean IS "
            "NOT NULL) + (value_date IS NOT NULL)) = 1)",
            name="p76_check_2",
        ),
        CheckConstraint("value_date IS NULL OR value_date >= '1000-01-01'", name="p76_check_3"),
        CheckConstraint(
            "option_id IS NOT NULL OR ("
            "(value_type = 'TEXT' AND value_text IS NOT NULL AND unit_id IS NULL) OR "
            "(value_type = 'INTEGER' AND value_integer IS NOT NULL) OR "
            "(value_type = 'DECIMAL' AND value_decimal IS NOT NULL) OR "
            "(value_type = 'BOOLEAN' AND value_boolean IS NOT NULL AND unit_id IS NULL) OR "
            "(value_type = 'DATE' AND value_date IS NOT NULL AND unit_id IS NULL))",
            name="p76_scalar_type",
        ),
        Index("ix_p76_0", "tenant_id", "company_id", "item_id", "id"),
        Index("ix_p76_1", "tenant_id", "company_id", "definition_id", "id"),
        Index("ix_p76_2", "tenant_id", "company_id", "option_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    option_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    value_type: Mapped[str] = mapped_column(String(10), nullable=False)
    value_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value_integer: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value_decimal: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ItemVariantKey(ProductDefinitionRow):
    __tablename__ = "item_variant_key"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p77_0"),
        UniqueConstraint(
            "tenant_id", "company_id", "family_id", "combination_hash", name="uq_p77_1"
        ),
        UniqueConstraint("tenant_id", "company_id", "item_id", name="uq_p77_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_p77_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_p77_1",
        ),
        CheckConstraint("row_version >= 1", name="p77_check_0"),
        Index("ix_p77_0", "tenant_id", "company_id", "family_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    combination_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(mysql.BINARY(32), "mysql"), nullable=False
    )
    canonical_combination: Mapped[bytes] = mapped_column(
        LargeBinary(2048).with_variant(mysql.VARBINARY(2048), "mysql"), nullable=False
    )


class ItemUnitBinding(ProductDefinitionRow):
    __tablename__ = "item_unit_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p78_0"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "id", name="uq_p78_item"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "code", name="uq_p78_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_p78_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_p78_1",
        ),
        CheckConstraint("row_version >= 1", name="p78_check_0"),
        CheckConstraint(
            "usage_role IN ('BASE','SALE','PURCHASE','BOTH','PACK','MEASURED')",
            name="p78_check_1",
        ),
        Index("ix_p78_0", "tenant_id", "company_id", "item_id", "id"),
        Index("ix_p78_1", "tenant_id", "company_id", "unit_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    usage_role: Mapped[str] = mapped_column(String(12), nullable=False)


class ItemUnitRevision(ProductDefinitionRow):
    __tablename__ = "item_unit_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p79_0"),
        UniqueConstraint("tenant_id", "company_id", "binding_id", "revision", name="uq_p79_1"),
        UniqueConstraint("tenant_id", "company_id", "binding_id", "valid_from", name="uq_p79_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "binding_id"],
            ["item_unit_binding.tenant_id", "item_unit_binding.company_id", "item_unit_binding.id"],
            name="fk_p79_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "pack_type_id"],
            ["pack_type.tenant_id", "pack_type.company_id", "pack_type.id"],
            name="fk_p79_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "secondary_unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_p79_2",
        ),
        CheckConstraint("row_version >= 1", name="p79_check_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="p79_check_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="p79_check_2"),
        CheckConstraint("revision >= 1", name="p79_check_3"),
        CheckConstraint(
            "quantity_decimal_places BETWEEN 0 AND 4 AND quantity_increment > 0",
            name="p79_check_4",
        ),
        CheckConstraint(
            "(conversion_mode = 'FIXED' AND numerator > 0 AND denominator > 0 AND numerator "
            "IS NOT NULL AND denominator IS NOT NULL AND nominal_ratio IS NULL AND "
            "secondary_unit_id IS NULL) OR (conversion_mode = 'MEASURED' AND numerator IS "
            "NULL AND denominator IS NULL AND nominal_ratio > 0 AND nominal_ratio IS NOT "
            "NULL AND secondary_unit_id IS NOT NULL)",
            name="p79_check_5",
        ),
        Index("ix_p79_0", "tenant_id", "company_id", "binding_id", "valid_from", "id"),
        Index("ix_p79_1", "tenant_id", "company_id", "pack_type_id", "id"),
        Index("ix_p79_2", "tenant_id", "company_id", "secondary_unit_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    binding_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    pack_type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    conversion_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    numerator: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    denominator: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nominal_ratio: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    secondary_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    quantity_decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_increment: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    fractional_entry: Mapped[bool] = mapped_column(Boolean, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class ItemBarcode(ProductDefinitionRow):
    __tablename__ = "item_barcode"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p80_0"),
        UniqueConstraint("tenant_id", "company_id", "value", name="uq_p80_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_p80_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id", "binding_id"],
            [
                "item_unit_binding.tenant_id",
                "item_unit_binding.company_id",
                "item_unit_binding.item_id",
                "item_unit_binding.id",
            ],
            name="fk_p80_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "identifier_type_code"],
            ["identifier_type.tenant_id", "identifier_type.company_id", "identifier_type.code"],
            name="fk_item_barcode_identifier_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "namespace_code"],
            [
                "identifier_namespace.tenant_id",
                "identifier_namespace.company_id",
                "identifier_namespace.code",
            ],
            name="fk_item_barcode_namespace",
        ),
        CheckConstraint("row_version >= 1", name="p80_check_0"),
        CheckConstraint("symbology IN ('GTIN','CODE128','QR')", name="p80_check_1"),
        Index("ix_p80_0", "tenant_id", "company_id", "item_id", "id"),
        Index("ix_p80_1", "tenant_id", "company_id", "binding_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    binding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    value: Mapped[str] = mapped_column(
        String(128).with_variant(mysql.VARCHAR(128, collation="utf8mb4_bin"), "mysql"),
        nullable=False,
    )
    symbology: Mapped[str] = mapped_column(String(12), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # v1 widening: an ``item_barcode`` row is the ``ProductIdentifier``. A NULL
    # ``identifier_type_code`` denotes the legacy barcode-only shape; a
    # non-null value binds the row to a mastered identifier type (MPN, GTIN,
    # SKU, or a tenant-private type). The table rename moves to v1.1.
    identifier_type_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    namespace_code: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ProductConfigurationAdoption(ProductDefinitionRow):
    __tablename__ = "product_configuration_adoption"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p81_0"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "revision", name="uq_p81_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_p81_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "product_type_revision_id"],
            [
                "product_type_revision.tenant_id",
                "product_type_revision.company_id",
                "product_type_revision.id",
            ],
            name="fk_p81_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_assignment_id"],
            [
                "family_group_assignment.tenant_id",
                "family_group_assignment.company_id",
                "family_group_assignment.id",
            ],
            name="fk_p81_2",
        ),
        CheckConstraint("row_version >= 1", name="p81_check_0"),
        CheckConstraint(
            "revision >= 1 AND source_version >= 1 AND policy_generation >= 1",
            name="p81_check_1",
        ),
        CheckConstraint("effective_on >= '1000-01-01'", name="p81_check_2"),
        Index("ix_p81_0", "tenant_id", "company_id", "item_id", "effective_on", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    product_type_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    group_assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Existing pins use v1 ordering; native Company-only adoption explicitly writes v2.
    resolution_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    preview_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(mysql.BINARY(32), "mysql"), nullable=False
    )


class ProductConfigurationAdoptionSource(ProductDefinitionRow):
    __tablename__ = "product_configuration_adoption_source"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_p82_0"),
        UniqueConstraint("tenant_id", "company_id", "adoption_id", "scope_id", name="uq_p82_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "adoption_id"],
            [
                "product_configuration_adoption.tenant_id",
                "product_configuration_adoption.company_id",
                "product_configuration_adoption.id",
            ],
            name="fk_p82_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scope_id"],
            [
                "product_configuration_scope.tenant_id",
                "product_configuration_scope.company_id",
                "product_configuration_scope.id",
            ],
            name="fk_p82_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scope_id", "revision_id"],
            [
                "product_configuration_revision.tenant_id",
                "product_configuration_revision.company_id",
                "product_configuration_revision.scope_id",
                "product_configuration_revision.id",
            ],
            name="fk_p82_2",
        ),
        CheckConstraint("row_version >= 1", name="p82_check_0"),
        Index("ix_p82_0", "tenant_id", "company_id", "adoption_id", "id"),
        Index("ix_p82_1", "tenant_id", "company_id", "revision_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    adoption_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


PRODUCT_DEFINITION_MODELS = (
    FamilyGroupAssignment,
    FamilyCategory,
    FamilyManufacturer,
    FamilyAttribute,
    FamilyAttributeOption,
    ItemAttributeValue,
    ItemVariantKey,
    ItemUnitBinding,
    ItemUnitRevision,
    ItemBarcode,
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
)
