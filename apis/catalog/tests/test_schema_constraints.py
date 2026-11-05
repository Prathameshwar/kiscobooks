"""Keep explicit native constraint names stable across metadata-created databases."""

from sqlalchemy import CheckConstraint

from catalog.metadata import service_metadata


def test_explicit_check_names_match_native_migrations() -> None:
    expected = {
        "compound_unit_component": [
            "ck_compound_unit_component_not_self",
            "ck_compound_unit_component_ordinal",
            "ck_compound_unit_component_quantity",
            "ck_compound_unit_component_row_version",
        ],
        "customer_pricing_projection": [
            "ck_customer_pricing_projection_dates",
            "ck_customer_pricing_projection_source_version",
        ],
        "customer_type_projection": ["ck_customer_type_projection_source_version"],
        "identifier_namespace": ["ck_identifier_namespace_row_version"],
        "identifier_type": ["ck_identifier_type_row_version"],
        "item_regulatory_classification": [
            "ck_item_regulatory_class_shape",
            "ck_item_regulatory_dates",
            "ck_item_regulatory_kind",
            "ck_item_regulatory_version",
        ],
        "party_projection": ["ck_party_projection_source_version"],
        "price_level_assignment": ["ck_pla_dates", "ck_pla_row_version"],
        "price_level_assignment_scope": ["ck_pla_scope_row_version", "ck_pla_scope_subject"],
        "sales_channel": ["ck_sales_channel_row_version"],
        "tax_rule": ["ck_tax_rule_classification_scope"],
    }
    metadata = service_metadata()
    for table, names in expected.items():
        actual = {
            str(c.name)
            for c in metadata.tables[table].constraints
            if isinstance(c, CheckConstraint)
        }
        assert set(names) <= actual, table
