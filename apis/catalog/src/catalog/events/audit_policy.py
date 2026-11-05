"""Catalog-owned categories and safe scalar vocabulary, intersected with each native entity."""

from catalog.domain.field_registry import registry

MONEY_ENTITIES = frozenset(
    """
price_level price_plan company_pricing_policy item_price_scope item_price_numeric_revision
item_price_series item_price_draft item_price item_price_tier purchase_price_term
item_reference_cost item_mrp item_price_formula commercial_policy_scope commercial_guard_rule
discount_ceiling item_commercial_policy tax_rule_applicability tax_release tax_history_action
tax_impact_review
tax_classification tax_category tax_rule tax_rate_series tax_rate tax_rate_component
catalog_tax_scope catalog_tax_binding
""".split()
)

# Exact vocabulary, never suffix matching; labels and arbitrary/custom JSON stay markers.
SAFE_FIELDS = frozenset(
    """
product_family_sku_enabled classification_scope batch_enabled lot_id lot_mrp lot_currency lot_unit_id
multiple_price_levels_mode unit_prices_mode quantity_tiers_mode channel_prices_mode
additional_currencies_mode formula_prices_mode
is_active status state kind dimension decimal_places quantity_increment numerator denominator
from_unit_id canonical_unit_id unit_id valid_from valid_to effective_from effective_to
parent_id parent_group_id group_id scheme_id membership_mode is_required allowed_kind
brand_id manufacturer_id product_type_id family_id item_id base_unit_id scope_id series_id
plan_id price_id draft_id revision_id source_draft_id template_revision_id identifier_profile_id
attribute_id attribute_definition_id attribute_set_id option_id unit_revision_id
revision latest_revision purpose currency rounding_mode rounding_method amount rate percentage
base_amount minimum_amount maximum_amount min_amount max_amount quantity min_quantity max_quantity
price_basis_quantity basis_quantity gross_amount net_amount discount_value price_increment
min_sale_quantity price_decimal_places numeric_revision_id price_scope_id
price value_type price_mode pricing_mode tax_inclusive discount_pct max_discount_pct margin_pct
factor multiplier rate_value taxable_percentage price_precision quantity_precision
country_code state_code tax_category_id tax_classification_id tax_rule_id tax_rate_id
rate_series_id source_version published_at adopted_at is_primary is_default sort_order
lot_tracking serial_tracking expiry_required manufacture_date_required shelf_life_days
minimum_remaining_life_days issue_strategy valuation_method inventory_affected free_sale_allowed
record_count completed_count invalid_count row_count progress processed_count
is_system main_warehouse_id transit_warehouse_id receipt_warehouse_id issue_warehouse_id
sales_warehouse_id purchase_warehouse_id manufacturing_warehouse_id return_warehouse_id
default_sale_warehouse_id default_purchase_warehouse_id default_opening_warehouse_id
default_customer_return_warehouse_id warehouse_id
allow_sale_issue allow_purchase_receipt allow_transfer_in allow_transfer_out
allow_customer_return_receipt allow_supplier_return_issue allow_opening_stock allow_adjustment
selection_mode scope_warehouse_id purchase_binding_id safety_quantity reorder_quantity
target_quantity min_order_quantity max_order_quantity order_multiple lead_time_days
effective_date policy_generation location_count default_count manifest_digest
release_id release_revision consumer aggregate aggregate_id enforced_revision result
reason_code source_message_id acknowledged_at
bom_id bom_revision_id draft_number component_count output_count line_key sequence
basis loss_fraction timing route_step_id route_revision_id nominal_quantity yield_fraction role
batch_minimum batch_maximum batch_multiple definition_date content_sha256 published_revision_id
maximum_applied group_count permission_count published_policy_id position stage selection
changes_basket include_reward_units earlier_group_id later_group_id policy_revision_id source_sha256
""".split()
)


def safe_fields(entity: str) -> frozenset[str]:
    if entity not in registry.entity_types():
        return frozenset()
    return frozenset(SAFE_FIELDS & registry.get(entity).fields.keys())


#: Entities no user ever writes. An acknowledgement arrives from a trusted consumer's signed
#: event, so its audit rows carry no actor and belong in the system category rather than the
#: administrative one a reader scans for human decisions (docs/audit.md §3).
SOURCE_ENTITIES = frozenset({"catalog.catalog_policy_consumer_ack", "catalog.stock_source_fence"})


def category(entity: str, action: str, *, system: bool = False) -> str:
    if entity == "catalog.import_job" and action == "cleanup":
        return "system"
    if action == "export":
        return "access"
    if entity in SOURCE_ENTITIES:
        return "system"
    if entity == "catalog.field_rebuild_job" and (system or action in {"cleanup", "failed"}):
        return "system"
    return "money" if entity.removeprefix("catalog.") in MONEY_ENTITIES else "admin"
