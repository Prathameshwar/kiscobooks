"""Company-owned descriptive families and SKU identities; never stock balances."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, Uuid7
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class ProductFamily(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "product_family"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_product_family_scope"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_product_family_code"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "product_type_revision_id"],
            [
                "product_type_revision.tenant_id",
                "product_type_revision.company_id",
                "product_type_revision.id",
            ],
            name="fk_product_family_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "brand_id"],
            ["brand.tenant_id", "brand.company_id", "brand.id"],
            name="fk_product_family_brand",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "brand_id", "series_id"],
            [
                "brand_series.tenant_id",
                "brand_series.company_id",
                "brand_series.brand_id",
                "brand_series.id",
            ],
            name="fk_product_family_series",
        ),
        Index("ix_product_family_name", "tenant_id", "company_id", "name", "id"),
        Index("ix_product_family_kind", "tenant_id", "company_id", "kind", "code", "id"),
        Index(
            "ix_product_family_type", "tenant_id", "company_id", "product_type_revision_id", "id"
        ),
        Index("ix_product_family_brand", "tenant_id", "company_id", "brand_id", "series_id"),
        CheckConstraint("kind IN ('GOODS', 'SERVICE')", name="product_family_kind"),
        CheckConstraint("structure_mode IN ('SIMPLE', 'VARIANT')", name="product_family_structure"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'DISCONTINUED')", name="product_family_status"
        ),
        CheckConstraint(
            "series_id IS NULL OR brand_id IS NOT NULL", name="product_family_series_brand"
        ),
        CheckConstraint("row_version >= 1", name="product_family_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    structure_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="SIMPLE")
    product_type_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    series_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    model_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Item(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_item_scope"),
        UniqueConstraint("tenant_id", "company_id", "sku", name="uq_item_sku"),
        UniqueConstraint(
            "tenant_id", "company_id", "family_id", "default_slot", name="uq_item_default"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_item_family",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "base_unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_item_base_unit",
        ),
        Index("ix_item_name", "tenant_id", "company_id", "name", "id"),
        Index("ix_item_status", "tenant_id", "company_id", "status", "sku", "id"),
        Index("ix_item_family", "tenant_id", "company_id", "family_id", "sku", "id"),
        Index("ix_item_unit", "tenant_id", "company_id", "base_unit_id", "id"),
        Index("ix_item_unit_sku", "tenant_id", "company_id", "base_unit_id", "sku", "id"),
        CheckConstraint("default_slot IS NULL OR default_slot = 1", name="item_default_slot"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'DISCONTINUED')", name="item_status"),
        CheckConstraint(
            "min_sale_quantity IS NULL OR min_sale_quantity > 0", name="item_min_sale_quantity"
        ),
        CheckConstraint("row_version >= 1", name="item_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    default_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sku: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sellable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    purchasable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    min_sale_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
