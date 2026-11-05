"""Test helpers shared across the suite."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Dialect
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.types import TypeEngine

# Re-exported: `table_of` moved into the library once the service suites needed it
# too (CLAUDE.md §3 — a test helper written twice belongs in `libs/platform`).
from billing_platform.testing import table_of

SQLITE = sqlite.dialect()
MYSQL = mysql.dialect()

__all__ = ["MYSQL", "SQLITE", "bind", "result", "table_of"]


def bind(column_type: TypeEngine[Any], value: Any, dialect: Dialect = SQLITE) -> Any:
    """Push a value through a column type's bind processor.

    Deliberately ``Any`` on both ends: these tests feed the *wrong* type on
    purpose, which is the whole reason the processors validate.
    """
    processor = column_type.bind_processor(dialect)
    assert processor is not None, f"{type(column_type).__name__} has no bind processor"
    return processor(value)


def result(column_type: TypeEngine[Any], value: Any, dialect: Dialect = SQLITE) -> Any:
    """Push a driver value back through a column type's result processor."""
    processor = column_type.result_processor(dialect, None)
    assert processor is not None, f"{type(column_type).__name__} has no result processor"
    return processor(value)
