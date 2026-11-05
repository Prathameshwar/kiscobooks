"""Mastered identifier-type and identifier-namespace codes.

An ``item_barcode`` row (semantically a ``ProductIdentifier``) that names a
non-barcode identifier — MPN, SKU, GTIN family variant — binds to a mastered
``identifier_type`` via a composite FK. ``identifier_namespace`` groups values
under a namespace so ``GTIN`` in the retail-EAN namespace does not collide with
``GTIN`` in a tenant-private namespace.

The two masters live outside ``product_definitions`` because they are not
per-item state; every product identifier row *refers* to them.
"""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import Boolean, CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv


class IdentifierMasterRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class IdentifierType(IdentifierMasterRow):
    __tablename__ = "identifier_type"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_identifier_type_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_identifier_type_code"),
        CheckConstraint("row_version >= 1", name=conv("ck_identifier_type_row_version")),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_barcode: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class IdentifierNamespace(IdentifierMasterRow):
    __tablename__ = "identifier_namespace"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_identifier_namespace_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_identifier_namespace_code"),
        CheckConstraint("row_version >= 1", name=conv("ck_identifier_namespace_row_version")),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


IDENTIFIER_MASTER_MODELS = (IdentifierType, IdentifierNamespace)
