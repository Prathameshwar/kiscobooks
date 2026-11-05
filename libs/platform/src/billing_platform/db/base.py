"""Declarative base and the constraint naming convention.

The naming convention must be set before any model is written. MariaDB
auto-names indexes and constraints unpredictably, and an auto-named constraint
cannot be reliably dropped in an Alembic ``downgrade``. Retrofitting this after
ten revisions means an ALTER per constraint across ten tables.
See docs/identity-db-plan.md §1.3.
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}

#: Set explicitly on every table, never inherited from the server default.
#: A server rebuilt with a different default silently changes collation, and
#: collation changes comparison semantics on every VARCHAR key.
MARIADB_TABLE_ARGS: Final[dict[str, Any]] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
    "mysql_row_format": "DYNAMIC",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Shared declarative base. Every service model inherits from this."""

    metadata = metadata_obj

    def __repr__(self) -> str:
        pk = self.__mapper__.primary_key
        values = ", ".join(f"{c.name}={getattr(self, c.name)!r}" for c in pk)
        return f"<{type(self).__name__} {values}>"
