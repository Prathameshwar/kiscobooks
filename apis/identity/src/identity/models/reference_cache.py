"""Identity-owned global reference cache generation, committed with source changes."""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ReferenceCacheGeneration(IdMixin, Base):
    __tablename__ = "reference_cache_generation"
    __table_args__ = (
        UniqueConstraint("key", name="uq_reference_cache_generation_key"),
        MARIADB_TABLE_ARGS,
    )
    key: Mapped[str] = mapped_column(String(16), nullable=False)
    token: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
