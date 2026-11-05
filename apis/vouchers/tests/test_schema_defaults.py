"""Number-series and import defaults are part of the migrated SQL contract."""

import pytest
from sqlalchemy import DefaultClause

from vouchers.metadata import service_metadata


@pytest.mark.parametrize(
    ("table", "column", "expected"),
    [
        ("voucher_import_job", "duplicate_rule", "DATE_NUMBER_PARTY"),
        ("voucher_number_series", "suffix", "''"),
        ("voucher_number_series", "start_value", "1"),
        ("voucher_number_series", "numbering_mode", "AUTOMATIC"),
        ("voucher_number_series", "reset_policy", "FINANCIAL_YEAR"),
        ("voucher_number_series", "include_year", "1"),
    ],
)
def test_migration_defaults_are_retained(table: str, column: str, expected: str) -> None:
    default = service_metadata().tables[table].c[column].server_default
    assert isinstance(default, DefaultClause), f"missing server default: {table}.{column}"
    assert str(default.arg) == expected
