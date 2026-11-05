"""Identity-owned source serialization lock and immutable Catalog snapshot artifacts."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class CatalogSourceGeneration(IdMixin, TenantMixin, Base):
    __tablename__ = "catalog_source_generation"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_catalog_source_generation_tenant"),
        CheckConstraint("version >= 1", name="catalog_source_version"),
        MARIADB_TABLE_ARGS,
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CatalogSourceSnapshot(IdMixin, TenantMixin, Base):
    __tablename__ = "catalog_source_snapshot"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_catalog_source_snapshot_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "request_id", name="uq_catalog_source_snapshot_request"
        ),
        Index("ix_catalog_source_snapshot_expiry", "tenant_id", "expires_at", "id"),
        CheckConstraint("source_version >= 1", name="catalog_snapshot_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CatalogSourcePage(IdMixin, TenantMixin, Base):
    __tablename__ = "catalog_source_page"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "snapshot_id",
            "page_number",
            name="uq_catalog_source_page_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "snapshot_id"],
            [
                "catalog_source_snapshot.tenant_id",
                "catalog_source_snapshot.company_id",
                "catalog_source_snapshot.id",
            ],
            name="fk_catalog_source_page_snapshot",
        ),
        CheckConstraint("page_number >= 0", name="catalog_source_page_nonnegative"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
