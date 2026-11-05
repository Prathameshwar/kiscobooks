"""Workflow evidence, separate from the 28 accounting master tables."""

import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Uuid7
from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from accounting.models.masters import Record


class MasterRevision(Record):
    __tablename__ = "accounting_master_revision"
    __table_args__ = (
        Index(
            "ix_accounting_revision_object",
            "tenant_id",
            "company_id",
            "entity_type",
            "object_id",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    object_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class MappingDraft(Record):
    __tablename__ = "accounting_mapping_draft"
    __table_args__ = (
        Index("ix_accounting_mapping_draft_page", "tenant_id", "company_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_mapping_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
