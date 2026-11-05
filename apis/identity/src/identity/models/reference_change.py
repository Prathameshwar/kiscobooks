"""Immutable global catalog change journal; transactionally owned by Identity."""

from __future__ import annotations

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class ReferenceChange(IdMixin, Base):
    __tablename__ = "reference_change"
    __table_args__ = (MARIADB_TABLE_ARGS,)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
