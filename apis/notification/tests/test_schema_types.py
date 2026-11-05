"""Retain exact migrated types for callback keys, trace identifiers and priority."""

import pytest
from sqlalchemy.dialects import mysql

from notification.metadata import service_metadata


@pytest.mark.parametrize(
    ("table", "column", "length"),
    [("provider_account", "callback_key", 43), ("notification_request", "trace_id", 32)],
)
def test_native_ascii_identifiers_keep_binary_comparison(
    table: str, column: str, length: int
) -> None:
    native = service_metadata().tables[table].c[column].type.dialect_impl(mysql.dialect())
    assert isinstance(native, mysql.CHAR)
    assert native.length == length
    assert native.charset == "ascii"
    assert native.collation == "ascii_bin"


def test_native_priority_keeps_its_unsigned_tinyint_storage() -> None:
    native = (
        service_metadata()
        .tables["notification_request"]
        .c.priority.type.dialect_impl(mysql.dialect())
    )
    assert isinstance(native, mysql.TINYINT)
    assert native.unsigned
