"""Typed authoring controls for existing reusable profile identities and revisions."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

MASTERS = {
    "catalog.inventory_profile_template",
    "catalog.manufacturing_operation",
    "catalog.manufacturing_route",
    "catalog.warranty_policy",
    "catalog.return_policy",
    "catalog.handling_profile",
}
REVISIONS = {entity + "_revision" for entity in MASTERS}
PUBLISH_PERMISSIONS = {
    "catalog.manufacturing_route_revision": "manufacturing_route.publish",
    "catalog.manufacturing_route_step": "manufacturing_route.publish",
    "catalog.manufacturing_operation_revision": "manufacturing_operation.publish",
    "catalog.inventory_profile_template_revision": "inventory_profile_template.publish",
    "catalog.warranty_policy_revision": "warranty_policy.publish",
    "catalog.return_policy_revision": "return_policy.publish",
    "catalog.return_policy_condition": "return_policy.publish",
    "catalog.handling_profile_revision": "handling_profile.publish",
}
CHOICES = {
    "time_basis": [("PER_OUTPUT_UNIT", "Per output unit"), ("PER_BATCH", "Per batch")],
    "issue_strategy": [("FIFO", "First in, first out"), ("FEFO", "First expiry, first out")],
    "valuation_method": [
        ("FIFO", "FIFO"),
        ("MOVING_AVERAGE", "Moving average"),
        ("SPECIFIC", "Specific"),
    ],
    "negative_stock_policy": [("BLOCK", "Block"), ("WARN", "Warn"), ("ALLOW", "Allow")],
    "duration_unit": [("DAYS", "Days"), ("MONTHS", "Months"), ("YEARS", "Years")],
    "start_trigger": [("SALE", "Sale"), ("DELIVERY", "Delivery"), ("INSTALLATION", "Installation")],
    "temperature_unit": [("CELSIUS", "Celsius")],
    "condition_code": [
        ("ORIGINAL_PACKAGING", "Original packaging"),
        ("PROOF_OF_PURCHASE", "Proof of purchase"),
        ("COMPLETE_ACCESSORIES", "Complete accessories"),
        ("UNUSED", "Unused"),
        ("UNDAMAGED", "Undamaged"),
    ],
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in MASTERS | REVISIONS | {
        "catalog.return_policy_condition",
        "catalog.manufacturing_route_step",
    }:
        return None
    label = key.replace("_", " ").capitalize()
    if key in {"code", "name", "temperature_min", "temperature_max"}:
        return ConfigurationControl(
            kind="text",
            label={
                "temperature_min": "Minimum temperature",
                "temperature_max": "Maximum temperature",
            }.get(key, label),
            max_length=30 if key == "code" else 100 if key == "name" else 21,
            nullable=key.startswith("temperature_"),
        )
    if key in {"setup_minutes", "run_minutes", "lead_time_minutes", "quantity_basis"}:
        return ConfigurationControl(kind="decimal", label=label, max_length=21, nullable=False)
    if key == "sequence":
        return ConfigurationControl(kind="integer", label="Step", minimum=1, maximum=50)
    if key == "operation_revision_id":
        return ConfigurationControl(
            kind="reference",
            label="Operation revision",
            reference_source="manufacturing-operation-revisions",
            nullable=False,
        )
    if key in {"instructions", "coverage_description", "specification", "change_reason"}:
        return ConfigurationControl(
            kind="text",
            label=label,
            max_length=500 if key == "change_reason" else 2000,
            nullable=key not in {"specification", "change_reason"},
        )
    if key in {
        "is_active",
        "lot_tracking",
        "serial_tracking",
        "expiry_required",
        "manufacture_date_required",
        "returns_allowed",
        "fragile",
        "keep_dry",
        "keep_upright",
    }:
        return ConfigurationControl(
            kind="boolean", label="Batch / lot tracking" if key == "lot_tracking" else label
        )
    if key in {"shelf_life_days", "minimum_remaining_life_days", "duration", "window_days"}:
        return ConfigurationControl(
            kind="integer",
            label=label,
            minimum=0 if key in {"minimum_remaining_life_days", "window_days"} else 1,
            maximum=36500,
            nullable=key != "duration",
        )
    if key in CHOICES:
        return ConfigurationControl(
            kind="select",
            label=label,
            nullable=key == "temperature_unit",
            choices=[ConfigurationChoice(value=value, label=text) for value, text in CHOICES[key]],
        )
    if key == "identifier_profile_id":
        return ConfigurationControl(
            kind="reference",
            label="Identifier profile",
            nullable=True,
            reference_source="identifier-profiles",
        )
    if key == "service_item_id":
        return ConfigurationControl(
            kind="reference",
            label="Service SKU",
            nullable=True,
            reference_source="items",
        )
    return None
