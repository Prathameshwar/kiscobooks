"""Opt-in shared ISO 639-1 materialization; imported by migrated services only."""

from sqlalchemy import CHAR, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base


class Language(Base):
    __tablename__ = "language"
    __table_args__ = (UniqueConstraint("iso3", name="uq_language_iso3"), MARIADB_TABLE_ARGS)

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    iso3: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    native_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
