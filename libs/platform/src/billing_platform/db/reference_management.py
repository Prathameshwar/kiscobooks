"""Service-local provenance for managed global reference materializations.

Intentionally no tenant: platform configuration, written only by its authenticated
owner or a verified replication worker. Natural ISO tables retain their own keys.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin
from billing_platform.db.types import Uuid7


class ReferenceRevision(IdMixin, AuditMixin, Base):
    __tablename__ = "reference_revision"
    __table_args__ = (
        UniqueConstraint("kind", "code", name="uq_reference_revision_kind_code"),
        Index("ix_reference_revision_kind_name_code", "kind", "name", "code"),
        Index("ix_reference_revision_kind_active_name_code", "kind", "is_active", "name", "code"),
        Index("ix_reference_revision_kind_parent_name_code", "kind", "parent_code", "name", "code"),
        MARIADB_TABLE_ARGS,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class ReferenceSyncState(IdMixin, Base):
    __tablename__ = "reference_sync_state"
    __table_args__ = (
        UniqueConstraint("service", name="uq_reference_sync_state_service"),
        MARIADB_TABLE_ARGS,
    )
    service: Mapped[str] = mapped_column(String(32), nullable=False)
    cursor: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
