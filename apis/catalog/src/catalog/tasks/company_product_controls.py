"""Company capability presentation hints using verified local Identity facts."""

from catalog.schemas.field_metadata import ConfigurationControl
from catalog.tasks.bom_controls import ENTITIES as BOM_ENTITIES

TYPE = "catalog.product_type_revision"
INVENTORY = "catalog.inventory_profile_template_revision"
TRACKING = {
    "BATCH": {"inventory", "batch_tracking"},
    "SERIAL": {"inventory", "serial_tracking"},
    "BATCH_SERIAL": {"inventory", "batch_tracking", "serial_tracking"},
}
FIELDS = {
    (TYPE, "require_expiry"): {"inventory", "batch_tracking", "expiry_tracking"},
    (TYPE, "inventory_template_revision_id"): {"inventory"},
    (INVENTORY, "lot_tracking"): {"inventory", "batch_tracking"},
    (INVENTORY, "serial_tracking"): {"inventory", "serial_tracking"},
    (INVENTORY, "expiry_required"): {"inventory", "batch_tracking", "expiry_tracking"},
    (INVENTORY, "identifier_profile_id"): {"inventory", "serial_tracking"},
}


def company_control(
    entity: str, key: str, hint: ConfigurationControl | None, features: frozenset[str]
) -> ConfigurationControl | None:
    if hint is None:
        return None
    if entity == TYPE and key in {"inventory_modes", "tracking_modes"}:
        allowed = {"NONE"} | {value for value, required in TRACKING.items() if required <= features}
        if key == "inventory_modes":
            allowed = {"NON_STOCK"} | ({"STOCK"} if "inventory" in features else set())
        hint = hint.model_copy(
            update={"choices": [choice for choice in hint.choices if choice.value in allowed]}
        )
    required = FIELDS.get((entity, key), set())
    if entity in BOM_ENTITIES:
        required = {"inventory", "bom_definitions"}
    if missing := required - features:
        hint = hint.model_copy(
            update={
                "disabled_reason": "Enable "
                + ", ".join(sorted(value.replace("_", " ") for value in missing))
                + " in Company configuration before using this option."
            }
        )
    if (
        entity == "catalog.product_pricing_policy"
        and key == "sale_level_count"
        and "multi_price_levels" not in features
    ):
        hint = hint.model_copy(update={"maximum": 1})
    if (
        entity == "catalog.product_pricing_policy"
        and key == "additional_currencies_mode"
        and "multi_currency" not in features
    ):
        hint = hint.model_copy(
            update={"choices": [choice for choice in hint.choices if choice.value != "ENABLED"]}
        )
    if (
        entity == "catalog.product_pricing_policy"
        and key == "multiple_price_levels_mode"
        and "multi_price_levels" not in features
    ):
        hint = hint.model_copy(
            update={"choices": [choice for choice in hint.choices if choice.value != "ENABLED"]}
        )
    if entity == "catalog.item_unit_revision":
        mode = (
            "FIXED"
            if key in {"numerator", "denominator"}
            else "MEASURED"
            if key in {"nominal_ratio", "secondary_unit_id"}
            else None
        )
        if mode:
            hint = hint.model_copy(update={"depends_on": "conversion_mode", "show_when": mode})
    return hint
