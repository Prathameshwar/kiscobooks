"""Closed Catalog-owned reference option contracts, never URLs or SQL."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OptionSource:
    entity: str
    parent_source: str | None = None
    parent_field: str | None = None


OPTION_SOURCES = {
    "catalog.tax_categories": OptionSource("catalog.tax_category"),
    "catalog.tax_rules": OptionSource("catalog.tax_rule"),
    "catalog.tax_classifications": OptionSource("catalog.tax_classification"),
    "catalog.handling_profiles": OptionSource("catalog.handling_profile"),
    "catalog.return_policies": OptionSource("catalog.return_policy"),
    "catalog.warranty_policies": OptionSource("catalog.warranty_policy"),
    "catalog.inventory_templates": OptionSource("catalog.inventory_profile_template"),
    "catalog.identifier_profiles": OptionSource("catalog.identifier_profile"),
    "catalog.units": OptionSource("catalog.unit_of_measure"),
    "catalog.pack_types": OptionSource("catalog.pack_type"),
    "catalog.item_groups": OptionSource("catalog.item_group"),
    "catalog.category_schemes": OptionSource("catalog.category_scheme"),
    "catalog.item_categories": OptionSource(
        "catalog.item_category", "catalog.category_schemes", "scheme_id"
    ),
    "catalog.brands": OptionSource("catalog.brand"),
    "catalog.brand_series": OptionSource("catalog.brand_series", "catalog.brands", "brand_id"),
    "catalog.manufacturers": OptionSource("catalog.manufacturer"),
    "catalog.manufacturer_sites": OptionSource(
        "catalog.manufacturer_site", "catalog.manufacturers", "manufacturer_id"
    ),
    "catalog.product_types": OptionSource("catalog.product_type"),
    "catalog.attribute_definitions": OptionSource("catalog.attribute_definition"),
    "catalog.attribute_options": OptionSource(
        "catalog.attribute_option", "catalog.attribute_definitions", "definition_id"
    ),
    "catalog.attribute_sets": OptionSource("catalog.attribute_set"),
}
