"""Scoped metadata references to code-registered Catalog masters."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import (
    AuditMixin,
    DeactivableMixin,
    IdMixin,
    TenantMixin,
)
from billing_platform.db.types import Uuid7
from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column


class MasterReference(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MasterAlias(MasterReference):
    __tablename__ = "master_alias"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_master_alias_scope"),
        CheckConstraint(
            "entity_type IN ('catalog.unit_of_measure', "
            "'catalog.pack_type', "
            "'catalog.item_group', "
            "'catalog.category_scheme', "
            "'catalog.item_category', "
            "'catalog.product_type', "
            "'catalog.brand', "
            "'catalog.brand_series', "
            "'catalog.manufacturer', "
            "'catalog.manufacturer_site', "
            "'catalog.attribute_definition', "
            "'catalog.attribute_option', "
            "'catalog.attribute_set', "
            "'catalog.identifier_profile', "
            "'catalog.inventory_profile_template', "
            "'catalog.warranty_policy', "
            "'catalog.return_policy', "
            "'catalog.handling_profile', 'catalog.tax_category', 'catalog.tax_rule', "
            "'catalog.tax_classification')",
            name="master_alias_entity",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "entity_type",
            "canonical_value",
            name="uq_master_alias_identity",
        ),
        Index(
            "ix_master_alias_owner",
            "tenant_id",
            "company_id",
            "entity_type",
            "target_id",
            "canonical_value",
            "id",
        ),
        Index(
            "ix_master_alias_active",
            "tenant_id",
            "company_id",
            "entity_type",
            "target_id",
            "is_active",
            "canonical_value",
            "id",
        ),
        CheckConstraint(
            "alias <> '' AND canonical_value <> ''",
            name="master_alias_lengths",
        ),
        CheckConstraint(
            "row_version >= 1 AND normalization_version = 1",
            name="master_alias_versions",
        ),
        Index(
            "ix_master_alias_owner_id",
            "tenant_id",
            "company_id",
            "entity_type",
            "target_id",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_value: Mapped[str] = mapped_column(
        String(200).with_variant(mysql.VARCHAR(200, collation="utf8mb4_bin"), "mysql"),
        nullable=False,
    )
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False)


class MasterExternalKey(MasterReference):
    __tablename__ = "master_external_key"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_master_external_key_scope"),
        CheckConstraint(
            "entity_type IN ('catalog.unit_of_measure', "
            "'catalog.pack_type', "
            "'catalog.item_group', "
            "'catalog.category_scheme', "
            "'catalog.item_category', "
            "'catalog.product_type', "
            "'catalog.brand', "
            "'catalog.brand_series', "
            "'catalog.manufacturer', "
            "'catalog.manufacturer_site', "
            "'catalog.attribute_definition', "
            "'catalog.attribute_option', "
            "'catalog.attribute_set', "
            "'catalog.identifier_profile', "
            "'catalog.inventory_profile_template', "
            "'catalog.warranty_policy', "
            "'catalog.return_policy', "
            "'catalog.handling_profile', 'catalog.tax_category', 'catalog.tax_rule', "
            "'catalog.tax_classification')",
            name="master_external_key_entity",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "entity_type",
            "source_namespace",
            "external_key",
            name="uq_master_external_key_identity",
        ),
        Index(
            "ix_master_external_key_owner",
            "tenant_id",
            "company_id",
            "entity_type",
            "target_id",
            "id",
        ),
        Index(
            "ix_master_external_key_source",
            "tenant_id",
            "company_id",
            "entity_type",
            "target_id",
            "source_namespace",
            "id",
        ),
        Index(
            "ix_master_external_key_active",
            "tenant_id",
            "company_id",
            "entity_type",
            "target_id",
            "is_active",
            "id",
        ),
        CheckConstraint(
            "source_namespace <> '' AND external_key <> ''",
            name="master_external_key_lengths",
        ),
        CheckConstraint("row_version >= 1", name="master_external_key_version"),
        MARIADB_TABLE_ARGS,
    )
    source_namespace: Mapped[str] = mapped_column(
        String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), nullable=False
    )
    external_key: Mapped[str] = mapped_column(
        String(200).with_variant(mysql.VARCHAR(200, collation="utf8mb4_bin"), "mysql"),
        nullable=False,
    )
