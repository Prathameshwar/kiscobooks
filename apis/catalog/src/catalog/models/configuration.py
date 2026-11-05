"""Native Product Configuration aggregates; drafts remain separate from immutable releases."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Money, Quantity, UtcDateTime, Uuid7
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.domain.pricing_dimensions import PRICING_DIMENSIONS


class ConfigurationRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class ProductConfigurationScope(ConfigurationRow):
    __tablename__ = "product_configuration_scope"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_product_configuration_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "scope_kind",
            "owner_id",
            name="uq_product_configuration_scope_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "product_type_id"],
            ["product_type.tenant_id", "product_type.company_id", "product_type.id"],
            name="fk_configuration_scope_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["item_group.tenant_id", "item_group.company_id", "item_group.id"],
            name="fk_configuration_scope_group",
        ),
        CheckConstraint(
            "(scope_kind = 'COMPANY' AND owner_id = company_id AND product_type_id IS "
            "NULL AND group_id IS NULL AND family_id IS NULL AND item_id IS NULL) OR "
            "(scope_kind = 'TYPE' AND owner_id = product_type_id AND product_type_id "
            "IS NOT NULL AND group_id IS NULL AND family_id IS NULL AND item_id IS "
            "NULL) OR (scope_kind = 'GROUP' AND owner_id = group_id AND "
            "product_type_id IS NULL AND group_id IS NOT NULL AND family_id IS NULL "
            "AND item_id IS NULL) OR (scope_kind = 'FAMILY' AND owner_id = family_id "
            "AND product_type_id IS NULL AND group_id IS NULL AND family_id IS NOT "
            "NULL AND item_id IS NULL) OR (scope_kind = 'SKU' AND owner_id = item_id "
            "AND product_type_id IS NULL AND group_id IS NULL AND family_id IS NULL "
            "AND item_id IS NOT NULL)",
            name="configuration_scope_owner",
        ),
        CheckConstraint(
            "row_version >= 1 AND latest_revision >= 0",
            name="configuration_scope_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_config_scope_family_id",
        ),
        Index("ix_config_scope_family_id", "tenant_id", "company_id", "family_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_config_scope_item_id",
        ),
        Index("ix_config_scope_item_id", "tenant_id", "company_id", "item_id", "id"),
        Index("ix_configuration_scope_kind", "tenant_id", "company_id", "scope_kind", "id"),
        Index("ix_configuration_scope_group", "tenant_id", "company_id", "group_id", "id"),
        Index(
            "ix_configuration_scope_type",
            "tenant_id",
            "company_id",
            "product_type_id",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    scope_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    product_type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    family_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProductConfigurationDraft(ConfigurationRow):
    __tablename__ = "product_configuration_draft"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_configuration_draft_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "scope_id",
            "id",
            name="uq_configuration_draft_scope_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scope_id"],
            [
                "product_configuration_scope.tenant_id",
                "product_configuration_scope.company_id",
                "product_configuration_scope.id",
            ],
            name="fk_configuration_draft_scope",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED') AND row_version >= 1",
            name="configuration_draft_status",
        ),
        CheckConstraint("effective_from >= '1000-01-01'", name="configuration_draft_date"),
        Index("ix_configuration_draft_scope", "tenant_id", "company_id", "scope_id", "id"),
        Index(
            "ix_configuration_draft_status",
            "tenant_id",
            "company_id",
            "scope_id",
            "status",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="DRAFT")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(250), nullable=False)


class ProductConfigurationRevision(ConfigurationRow):
    __tablename__ = "product_configuration_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_configuration_revision_id"),
        UniqueConstraint(
            "tenant_id", "company_id", "scope_id", "id", name="uq_configuration_revision_scope_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "scope_id",
            "revision",
            name="uq_configuration_revision_number",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_draft_id",
            name="uq_configuration_revision_draft",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scope_id", "source_draft_id"],
            [
                "product_configuration_draft.tenant_id",
                "product_configuration_draft.company_id",
                "product_configuration_draft.scope_id",
                "product_configuration_draft.id",
            ],
            name="fk_configuration_revision_draft",
        ),
        CheckConstraint("revision >= 1", name="configuration_revision_number"),
        CheckConstraint("effective_from >= '1000-01-01'", name="configuration_revision_date"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "scope_id",
            "effective_from",
            name="uq_configuration_revision_date",
        ),
        Index("ix_configuration_revision_scope_id", "tenant_id", "company_id", "scope_id", "id"),
        Index(
            "ix_configuration_revision_effective",
            "tenant_id",
            "company_id",
            "scope_id",
            "effective_from",
            "revision",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_draft_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    published_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(250), nullable=False)


class ConfigurationChild(ConfigurationRow):
    __abstract__ = True
    draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ProductEntryOptionPolicy(ConfigurationChild):
    __tablename__ = "product_entry_option_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_entry_option_policy_id"),
        UniqueConstraint(
            "tenant_id", "company_id", "draft_id", name="uq_entry_option_policy_draft"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            name="uq_entry_option_policy_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "draft_id"],
            [
                "product_configuration_draft.tenant_id",
                "product_configuration_draft.company_id",
                "product_configuration_draft.id",
            ],
            name="fk_entry_option_policy_draft",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "product_configuration_revision.tenant_id",
                "product_configuration_revision.company_id",
                "product_configuration_revision.id",
            ],
            name="fk_entry_option_policy_revision",
        ),
        CheckConstraint(
            "(draft_id IS NULL) <> (revision_id IS NULL)",
            name="entry_option_policy_owner",
        ),
        CheckConstraint(
            "variants_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((variants_mode = 'OPTIONAL' AND variants_default IS NOT NULL) OR "
            "(variants_mode <> 'OPTIONAL' AND variants_default IS NULL))",
            name="entry_variants_mode",
        ),
        CheckConstraint(
            "barcode_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((barcode_mode = 'OPTIONAL' AND barcode_default IS NOT NULL) OR "
            "(barcode_mode <> 'OPTIONAL' AND barcode_default IS NULL))",
            name="entry_barcode_mode",
        ),
        CheckConstraint(
            "brand_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((brand_mode = 'OPTIONAL' AND brand_default IS NOT NULL) OR (brand_mode "
            "<> 'OPTIONAL' AND brand_default IS NULL))",
            name="entry_brand_mode",
        ),
        CheckConstraint(
            "model_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((model_mode = 'OPTIONAL' AND model_default IS NOT NULL) OR "
            "(model_mode <> 'OPTIONAL' AND model_default IS NULL))",
            name="entry_model_mode",
        ),
        CheckConstraint(
            "category_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((category_mode = 'OPTIONAL' AND category_default IS NOT NULL) OR "
            "(category_mode <> 'OPTIONAL' AND category_default IS NULL))",
            name="entry_category_mode",
        ),
        CheckConstraint(
            "manufacturer_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((manufacturer_mode = 'OPTIONAL' AND manufacturer_default IS NOT NULL) OR "
            "(manufacturer_mode <> 'OPTIONAL' AND manufacturer_default IS NULL))",
            name="entry_manufacturer_mode",
        ),
        CheckConstraint(
            "alternate_units_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((alternate_units_mode = 'OPTIONAL' AND alternate_units_default IS NOT "
            "NULL) OR (alternate_units_mode <> 'OPTIONAL' AND alternate_units_default "
            "IS NULL))",
            name="entry_alternate_units_mode",
        ),
        CheckConstraint(
            "compound_units_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((compound_units_mode = 'OPTIONAL' AND compound_units_default IS NOT "
            "NULL) OR (compound_units_mode <> 'OPTIONAL' AND compound_units_default IS "
            "NULL))",
            name="entry_compound_units_mode",
        ),
        CheckConstraint(
            "measured_units_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND "
            "((measured_units_mode = 'OPTIONAL' AND measured_units_default IS NOT "
            "NULL) OR (measured_units_mode <> 'OPTIONAL' AND measured_units_default IS "
            "NULL))",
            name="entry_measured_units_mode",
        ),
        MARIADB_TABLE_ARGS,
    )
    variants_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    variants_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    barcode_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    barcode_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    brand_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    brand_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    model_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )
    model_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    category_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    category_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manufacturer_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    manufacturer_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alternate_units_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    alternate_units_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    compound_units_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    compound_units_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    measured_units_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    measured_units_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class ProductNumericDefault(ConfigurationChild):
    __tablename__ = "product_numeric_default"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_numeric_default_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "draft_id",
            "dimension",
            name="uq_numeric_default_draft",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "dimension",
            name="uq_numeric_default_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "draft_id"],
            [
                "product_configuration_draft.tenant_id",
                "product_configuration_draft.company_id",
                "product_configuration_draft.id",
            ],
            name="fk_numeric_default_draft",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "product_configuration_revision.tenant_id",
                "product_configuration_revision.company_id",
                "product_configuration_revision.id",
            ],
            name="fk_numeric_default_revision",
        ),
        CheckConstraint(
            "(draft_id IS NULL) <> (revision_id IS NULL)", name="numeric_default_owner"
        ),
        CheckConstraint(
            "dimension IN ('COUNT','MASS','VOLUME','LENGTH','AREA','TIME','JOB')",
            name="numeric_default_dimension",
        ),
        CheckConstraint(
            "(quantity_decimal_places IS NULL AND quantity_increment IS NULL) OR "
            "(quantity_decimal_places IS NOT NULL AND quantity_increment IS NOT NULL "
            "AND quantity_decimal_places BETWEEN 0 AND 4 AND quantity_increment > 0)",
            name="numeric_default_quantity",
        ),
        CheckConstraint(
            "(price_decimal_places IS NULL AND currency IS NULL AND price_increment IS "
            "NULL) OR (price_decimal_places IS NOT NULL AND currency IS NOT NULL AND "
            "price_decimal_places BETWEEN 0 AND 4 AND (price_increment IS NULL OR "
            "price_increment > 0))",
            name="numeric_default_price",
        ),
        CheckConstraint(
            "price_basis_quantity IS NULL OR price_basis_quantity > 0",
            name="numeric_default_basis",
        ),
        MARIADB_TABLE_ARGS,
    )
    dimension: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity_decimal_places: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity_increment: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    price_decimal_places: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_increment: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    price_basis_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)


class CatalogDefaultProfile(ConfigurationChild):
    __tablename__ = "catalog_default_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_catalog_default_profile_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "draft_id",
            name="uq_catalog_default_profile_draft",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            name="uq_catalog_default_profile_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "draft_id"],
            [
                "product_configuration_draft.tenant_id",
                "product_configuration_draft.company_id",
                "product_configuration_draft.id",
            ],
            name="fk_catalog_default_profile_draft",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "product_configuration_revision.tenant_id",
                "product_configuration_revision.company_id",
                "product_configuration_revision.id",
            ],
            name="fk_catalog_default_profile_revision",
        ),
        CheckConstraint(
            "(draft_id IS NULL) <> (revision_id IS NULL)",
            name="catalog_default_profile_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "goods_type_revision_id"],
            [
                "product_type_revision.tenant_id",
                "product_type_revision.company_id",
                "product_type_revision.id",
            ],
            name="fk_default_goods_type_revision",
        ),
        CheckConstraint(
            "goods_type_revision_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((goods_type_revision_mode = 'VALUE' AND goods_type_revision_id IS NOT "
            "NULL) OR (goods_type_revision_mode <> 'VALUE' AND goods_type_revision_id "
            "IS NULL))",
            name="default_goods_type_revision_mode",
        ),
        Index(
            "ix_default_goods_type_revision",
            "tenant_id",
            "company_id",
            "goods_type_revision_id",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "service_type_revision_id"],
            [
                "product_type_revision.tenant_id",
                "product_type_revision.company_id",
                "product_type_revision.id",
            ],
            name="fk_default_service_type_revision",
        ),
        CheckConstraint(
            "service_type_revision_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((service_type_revision_mode = 'VALUE' AND service_type_revision_id IS "
            "NOT NULL) OR (service_type_revision_mode <> 'VALUE' AND "
            "service_type_revision_id IS NULL))",
            name="default_service_type_revision_mode",
        ),
        Index(
            "ix_default_service_type_revision",
            "tenant_id",
            "company_id",
            "service_type_revision_id",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "inventory_template_revision_id"],
            [
                "inventory_profile_template_revision.tenant_id",
                "inventory_profile_template_revision.company_id",
                "inventory_profile_template_revision.id",
            ],
            name="fk_default_inventory_template_revision",
        ),
        CheckConstraint(
            "inventory_template_revision_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((inventory_template_revision_mode = 'VALUE' AND "
            "inventory_template_revision_id IS NOT NULL) OR "
            "(inventory_template_revision_mode <> 'VALUE' AND "
            "inventory_template_revision_id IS NULL))",
            name="default_inventory_template_revision_mode",
        ),
        Index(
            "ix_default_inventory_template_revision",
            "tenant_id",
            "company_id",
            "inventory_template_revision_id",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warranty_revision_id"],
            [
                "warranty_policy_revision.tenant_id",
                "warranty_policy_revision.company_id",
                "warranty_policy_revision.id",
            ],
            name="fk_default_warranty_revision",
        ),
        CheckConstraint(
            "warranty_revision_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((warranty_revision_mode = 'VALUE' AND warranty_revision_id IS NOT NULL) "
            "OR (warranty_revision_mode <> 'VALUE' AND warranty_revision_id IS NULL))",
            name="default_warranty_revision_mode",
        ),
        Index(
            "ix_default_warranty_revision",
            "tenant_id",
            "company_id",
            "warranty_revision_id",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "return_policy_revision_id"],
            [
                "return_policy_revision.tenant_id",
                "return_policy_revision.company_id",
                "return_policy_revision.id",
            ],
            name="fk_default_return_policy_revision",
        ),
        CheckConstraint(
            "return_policy_revision_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((return_policy_revision_mode = 'VALUE' AND return_policy_revision_id IS "
            "NOT NULL) OR (return_policy_revision_mode <> 'VALUE' AND "
            "return_policy_revision_id IS NULL))",
            name="default_return_policy_revision_mode",
        ),
        Index(
            "ix_default_return_policy_revision",
            "tenant_id",
            "company_id",
            "return_policy_revision_id",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "handling_revision_id"],
            [
                "handling_profile_revision.tenant_id",
                "handling_profile_revision.company_id",
                "handling_profile_revision.id",
            ],
            name="fk_default_handling_revision",
        ),
        CheckConstraint(
            "handling_revision_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((handling_revision_mode = 'VALUE' AND handling_revision_id IS NOT NULL) "
            "OR (handling_revision_mode <> 'VALUE' AND handling_revision_id IS NULL))",
            name="default_handling_revision_mode",
        ),
        Index(
            "ix_default_handling_revision",
            "tenant_id",
            "company_id",
            "handling_revision_id",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "identifier_profile_id"],
            [
                "identifier_profile.tenant_id",
                "identifier_profile.company_id",
                "identifier_profile.id",
            ],
            name="fk_default_identifier_profile",
        ),
        CheckConstraint(
            "identifier_profile_mode IN ('INHERIT','CLEAR','VALUE') AND "
            "((identifier_profile_mode = 'VALUE' AND identifier_profile_id IS NOT "
            "NULL) OR (identifier_profile_mode <> 'VALUE' AND identifier_profile_id IS "
            "NULL))",
            name="default_identifier_profile_mode",
        ),
        Index(
            "ix_default_identifier_profile",
            "tenant_id",
            "company_id",
            "identifier_profile_id",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    goods_type_revision_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    goods_type_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    service_type_revision_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    service_type_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    inventory_template_revision_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    inventory_template_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    warranty_revision_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    warranty_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    return_policy_revision_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    return_policy_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    handling_revision_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    handling_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    identifier_profile_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    identifier_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ProductPricingPolicy(ConfigurationChild):
    __tablename__ = "product_pricing_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_pricing_policy_id"),
        UniqueConstraint("tenant_id", "company_id", "draft_id", name="uq_pricing_policy_draft"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", name="uq_pricing_policy_revision"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "draft_id"],
            [
                "product_configuration_draft.tenant_id",
                "product_configuration_draft.company_id",
                "product_configuration_draft.id",
            ],
            name="fk_pricing_policy_draft",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "product_configuration_revision.tenant_id",
                "product_configuration_revision.company_id",
                "product_configuration_revision.id",
            ],
            name="fk_pricing_policy_revision",
        ),
        CheckConstraint("(draft_id IS NULL) <> (revision_id IS NULL)", name="pricing_policy_owner"),
        CheckConstraint(
            "purchase_reference_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED')",
            name="pricing_purchase_reference_mode",
        ),
        CheckConstraint(
            "sale_price_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED')",
            name="pricing_sale_price_mode",
        ),
        CheckConstraint(
            "mrp_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED')",
            name="pricing_mrp_mode",
        ),
        CheckConstraint(
            "sale_level_count IS NULL OR sale_level_count BETWEEN 1 AND 64",
            name="pricing_level_count",
        ),
        *(
            CheckConstraint(f"{field} IN ('INHERIT','DISABLED','ENABLED')", name="pricing_" + field)
            for field in PRICING_DIMENSIONS
        ),
        MARIADB_TABLE_ARGS,
    )
    purchase_reference_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT"
    )
    sale_price_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    mrp_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="INHERIT")
    sale_level_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    multiple_price_levels_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )
    unit_prices_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )
    quantity_tiers_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )
    channel_prices_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )
    additional_currencies_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )
    formula_prices_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INHERIT", server_default="INHERIT"
    )


CONFIGURATION_MODELS = (
    ProductConfigurationScope,
    ProductConfigurationDraft,
    ProductConfigurationRevision,
    ProductEntryOptionPolicy,
    ProductNumericDefault,
    CatalogDefaultProfile,
    ProductPricingPolicy,
)
