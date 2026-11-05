"""Commercial product masters; parties and physical manufacturing remain external."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    CHAR,
    JSON,
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

from catalog.models.classification import ClassificationMaster


def master_constraints(name: str, parent: str | None = None) -> tuple[Any, ...]:
    scope = ["tenant_id", "company_id", *([parent] if parent else [])]
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope_id"),
        UniqueConstraint(*scope, "code", name=f"uq_{name}_scope_code"),
        Index(f"ix_{name}_name", "tenant_id", "company_id", "name", "id"),
        Index(f"ix_{name}_active_code", "tenant_id", "company_id", "is_active", "code", "id"),
        Index(f"ix_{name}_active_name", "tenant_id", "company_id", "is_active", "name", "id"),
        CheckConstraint("row_version >= 1", name=f"{name}_version"),
    )


class Brand(ClassificationMaster):
    __tablename__ = "brand"
    __table_args__ = (
        *master_constraints("brand"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "parent_brand_id"],
            ["brand.tenant_id", "brand.company_id", "brand.id"],
            name="fk_brand_parent",
        ),
        Index("ix_brand_parent", "tenant_id", "company_id", "parent_brand_id", "id"),
        CheckConstraint("parent_brand_id IS NULL OR parent_brand_id <> id", name="brand_self"),
        MARIADB_TABLE_ARGS,
    )
    parent_brand_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    owner_party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Manufacturer(ClassificationMaster):
    __tablename__ = "manufacturer"
    __table_args__ = (*master_constraints("manufacturer"), MARIADB_TABLE_ARGS)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class BrandSeries(ClassificationMaster):
    __tablename__ = "brand_series"
    __table_args__ = (
        *master_constraints("brand_series", "brand_id"),
        UniqueConstraint(
            "tenant_id", "company_id", "brand_id", "id", name="uq_brand_series_parent_id"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "brand_id"],
            ["brand.tenant_id", "brand.company_id", "brand.id"],
            name="fk_brand_series_brand",
        ),
        Index("ix_brand_series_code", "tenant_id", "company_id", "code", "id"),
        Index("ix_brand_series_parent_name", "tenant_id", "company_id", "brand_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class ManufacturerSite(ClassificationMaster):
    __tablename__ = "manufacturer_site"
    __table_args__ = (
        *master_constraints("manufacturer_site", "manufacturer_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "manufacturer_id",
            "id",
            name="uq_manufacturer_site_parent_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "manufacturer_id"],
            ["manufacturer.tenant_id", "manufacturer.company_id", "manufacturer.id"],
            name="fk_manufacturer_site_parent",
        ),
        ForeignKeyConstraint(
            ["country_code"], ["country.code"], name="fk_manufacturer_site_country"
        ),
        ForeignKeyConstraint(
            ["country_code", "state_code"],
            ["state.country_code", "state.code"],
            name="fk_manufacturer_site_state",
        ),
        Index("ix_manufacturer_site_country_state", "country_code", "state_code"),
        Index("ix_manufacturer_site_code", "tenant_id", "company_id", "code", "id"),
        Index(
            "ix_manufacturer_site_parent_name",
            "tenant_id",
            "company_id",
            "manufacturer_id",
            "name",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    state_code: Mapped[str | None] = mapped_column(String(6), nullable=True)


class BrandManufacturer(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "brand_manufacturer"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "brand_id",
            "manufacturer_id",
            "production_role",
            "valid_from",
            name="uq_brand_manufacturer_start",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "brand_id"],
            ["brand.tenant_id", "brand.company_id", "brand.id"],
            name="fk_brand_manufacturer_brand",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "manufacturer_id"],
            ["manufacturer.tenant_id", "manufacturer.company_id", "manufacturer.id"],
            name="fk_brand_manufacturer_manufacturer",
        ),
        Index("ix_brand_manufacturer_company", "tenant_id", "company_id", "valid_from", "id"),
        Index("ix_brand_manufacturer_source", "tenant_id", "company_id", "manufacturer_id", "id"),
        CheckConstraint(
            "production_role IN ('OEM', 'CONTRACT_MANUFACTURER', 'ASSEMBLER')",
            name="brand_manufacturer_role",
        ),
        CheckConstraint(
            "valid_from >= '1000-01-01' AND (valid_to IS NULL OR valid_to >= valid_from)",
            name="brand_manufacturer_dates",
        ),
        CheckConstraint("row_version >= 1", name="brand_manufacturer_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    production_role: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProductType(ClassificationMaster):
    __tablename__ = "product_type"
    __table_args__ = (
        *master_constraints("product_type"),
        CheckConstraint("kind IN ('GOODS', 'SERVICE', 'BOTH')", name="product_type_kind"),
        MARIADB_TABLE_ARGS,
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ProductTypeRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "product_type_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_product_type_revision_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "product_type_id",
            "revision",
            name="uq_product_type_revision_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "product_type_id"],
            ["product_type.tenant_id", "product_type.company_id", "product_type.id"],
            name="fk_product_type_revision_type",
        ),
        Index(
            "ix_product_type_revision_published",
            "tenant_id",
            "company_id",
            "product_type_id",
            "published_at",
            "revision",
            "id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "attribute_set_revision_id"],
            [
                "attribute_set_revision.tenant_id",
                "attribute_set_revision.company_id",
                "attribute_set_revision.id",
            ],
            name="fk_product_type_revision_attribute_set",
        ),
        Index(
            "ix_product_type_revision_attribute_set",
            "tenant_id",
            "company_id",
            "attribute_set_revision_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "inventory_template_revision_id"],
            [
                "inventory_profile_template_revision.tenant_id",
                "inventory_profile_template_revision.company_id",
                "inventory_profile_template_revision.id",
            ],
            name="fk_product_type_revision_inventory",
        ),
        Index(
            "ix_product_type_revision_inventory",
            "tenant_id",
            "company_id",
            "inventory_template_revision_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warranty_revision_id"],
            [
                "warranty_policy_revision.tenant_id",
                "warranty_policy_revision.company_id",
                "warranty_policy_revision.id",
            ],
            name="fk_product_type_revision_warranty",
        ),
        Index(
            "ix_product_type_revision_warranty", "tenant_id", "company_id", "warranty_revision_id"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "return_policy_revision_id"],
            [
                "return_policy_revision.tenant_id",
                "return_policy_revision.company_id",
                "return_policy_revision.id",
            ],
            name="fk_product_type_revision_return",
        ),
        Index(
            "ix_product_type_revision_return",
            "tenant_id",
            "company_id",
            "return_policy_revision_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "handling_revision_id"],
            [
                "handling_profile_revision.tenant_id",
                "handling_profile_revision.company_id",
                "handling_profile_revision.id",
            ],
            name="fk_product_type_revision_handling",
        ),
        Index(
            "ix_product_type_revision_handling", "tenant_id", "company_id", "handling_revision_id"
        ),
        CheckConstraint("revision >= 1 AND row_version >= 1", name="product_type_revision_version"),
        CheckConstraint("kind IN ('GOODS', 'SERVICE', 'BOTH')", name="product_type_revision_kind"),
        CheckConstraint(
            "allow_variants IN (0,1) AND require_brand IN (0,1) "
            "AND require_manufacturer IN (0,1) AND require_expiry IN (0,1)",
            name="product_type_revision_flags",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    product_type_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    attribute_set_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    inventory_template_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    warranty_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    return_policy_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    handling_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    inventory_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    tracking_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unit_dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allow_variants: Mapped[bool] = mapped_column(Boolean, nullable=False)
    require_brand: Mapped[bool] = mapped_column(Boolean, nullable=False)
    require_manufacturer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    require_expiry: Mapped[bool] = mapped_column(Boolean, nullable=False)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
