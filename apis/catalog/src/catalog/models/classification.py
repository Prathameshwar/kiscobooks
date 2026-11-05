"""Catalog classification definitions and the company policy-generation lock."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
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


class CatalogPolicyState(IdMixin, TenantMixin, Base):
    __tablename__ = "catalog_policy_state"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", name="uq_catalog_policy_state_company"),
        CheckConstraint("generation >= 1", name="catalog_policy_generation"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class ClassificationMaster(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ItemGroup(ClassificationMaster):
    __tablename__ = "item_group"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_item_group_scope_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_item_group_scope_code"),
        Index("ix_item_group_scope_name_id", "tenant_id", "company_id", "name", "id"),
        CheckConstraint("allowed_kind IN ('GOODS', 'SERVICE', 'BOTH')", name="item_group_kind"),
        CheckConstraint("row_version > 0", name="item_group_version"),
        MARIADB_TABLE_ARGS,
    )
    allowed_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class HierarchyEdge(IdMixin, TenantMixin, AuditMixin, Base):
    """One dated parent link in a company hierarchy. A ``NULL`` parent is a root.

    Shared by item groups and stock-location groups. The shape is the whole reason the two
    can run the same reparenting code: history is appended and closed, never rewritten, so
    "who was my parent on that date" keeps answering what it answered then.
    """

    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    parent_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class ItemGroupParent(HierarchyEdge):
    __tablename__ = "item_group_parent"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "group_id", "valid_from", name="uq_item_group_parent_start"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["item_group.tenant_id", "item_group.company_id", "item_group.id"],
            name="fk_item_group_parent_group",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "parent_group_id"],
            ["item_group.tenant_id", "item_group.company_id", "item_group.id"],
            name="fk_item_group_parent_parent",
        ),
        Index(
            "ix_item_group_parent_descendants",
            "tenant_id",
            "company_id",
            "parent_group_id",
            "valid_from",
            "id",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="item_group_parent_dates"
        ),
        CheckConstraint("valid_from >= '1000-01-01'", name="item_group_parent_date_range"),
        CheckConstraint(
            "parent_group_id IS NULL OR parent_group_id <> group_id", name="item_group_parent_self"
        ),
        MARIADB_TABLE_ARGS,
    )


class CategoryScheme(ClassificationMaster):
    __tablename__ = "category_scheme"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_category_scheme_scope_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_category_scheme_scope_code"),
        Index("ix_category_scheme_scope_name_id", "tenant_id", "company_id", "name", "id"),
        CheckConstraint("membership_mode IN ('SINGLE', 'MULTIPLE')", name="category_scheme_mode"),
        CheckConstraint("row_version > 0", name="category_scheme_version"),
        MARIADB_TABLE_ARGS,
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    membership_mode: Mapped[str] = mapped_column(String(10), nullable=False)


class ItemCategory(ClassificationMaster):
    __tablename__ = "item_category"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "scheme_id", "id", name="uq_item_category_scope_id"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "scheme_id", "code", name="uq_item_category_scope_code"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scheme_id"],
            ["category_scheme.tenant_id", "category_scheme.company_id", "category_scheme.id"],
            name="fk_item_category_scheme",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scheme_id", "parent_id"],
            [
                "item_category.tenant_id",
                "item_category.company_id",
                "item_category.scheme_id",
                "item_category.id",
            ],
            name="fk_item_category_parent",
        ),
        Index(
            "ix_item_category_scope_name_id", "tenant_id", "company_id", "scheme_id", "name", "id"
        ),
        Index("ix_item_category_company_code", "tenant_id", "company_id", "code", "id"),
        Index("ix_item_category_company_name", "tenant_id", "company_id", "name", "id"),
        Index("ix_item_category_parent", "tenant_id", "company_id", "scheme_id", "parent_id", "id"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="item_category_self"),
        CheckConstraint("row_version > 0", name="item_category_version"),
        MARIADB_TABLE_ARGS,
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
