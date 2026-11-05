"""Installation control record, outside tenant business-data filtering."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PlatformInstallation(IdMixin, Base):
    __tablename__ = "platform_installation"
    __table_args__ = (
        UniqueConstraint("key", name="uq_platform_installation_key"),
        MARIADB_TABLE_ARGS,
    )

    key: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    public_url: Mapped[str | None] = mapped_column(String(2048))
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    administrator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    administrator_subject: Mapped[str | None] = mapped_column(String(64))
    request_hash: Mapped[str | None] = mapped_column(String(64))
