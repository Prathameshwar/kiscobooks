"""Defaults retained by native migrations must also appear in ORM metadata."""

import pytest
from sqlalchemy import DefaultClause

from catalog.metadata import service_metadata


@pytest.mark.parametrize(
    ("table", "column", "expected"),
    [
        ("compound_unit_component", "row_version", "1"),
        ("family_category", "valid_from", "'1000-01-01'"),
        ("identifier_namespace", "row_version", "1"),
        ("identifier_type", "row_version", "1"),
        ("inventory_profile_template_revision", "negative_stock_policy", "BLOCK"),
        ("item_inventory_profile", "negative_stock_policy", "BLOCK"),
        ("price_level_assignment", "row_version", "1"),
        ("price_level_assignment_scope", "row_version", "1"),
        ("sales_channel", "row_version", "1"),
        ("sales_channel", "is_active", "1"),
        ("tax_rule", "classification_scope", "SPECIFIC"),
    ],
)
def test_migration_defaults_are_retained(table: str, column: str, expected: str) -> None:
    default = service_metadata().tables[table].c[column].server_default
    assert isinstance(default, DefaultClause), f"missing server default: {table}.{column}"
    assert str(default.arg) == expected
