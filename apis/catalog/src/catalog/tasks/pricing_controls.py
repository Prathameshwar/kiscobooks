"""Typed controls for native pricing masters; commands enforce business authority."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

ENTITIES = {"catalog.sales_channel", "catalog.price_level", "catalog.price_plan"}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in ENTITIES:
        return None
    label = key.replace("_", " ").capitalize()
    if key in {"code", "name"}:
        return ConfigurationControl(
            kind="text", label=label, max_length=30 if key == "code" else 100
        )
    if key == "is_active":
        return ConfigurationControl(kind="boolean", label="Active")
    if key == "ordinal":
        return ConfigurationControl(kind="integer", label="Level number", minimum=4, maximum=64)
    if key in {"purpose", "tax_basis"}:
        choices = (
            [("SALE", "Sale"), ("PURCHASE", "Purchase"), ("REFERENCE_RETAIL", "Reference retail")]
            if key == "purpose"
            else [("EXCLUSIVE", "Tax exclusive"), ("INCLUSIVE", "Tax inclusive")]
        )
        return ConfigurationControl(
            kind="select",
            label=label,
            choices=[ConfigurationChoice(value=value, label=text) for value, text in choices],
        )
    if key in {"price_level_id", "currency"}:
        return ConfigurationControl(
            kind="reference",
            label="Sales price level" if key == "price_level_id" else "Currency",
            reference_source="price-levels" if key == "price_level_id" else "currencies",
            nullable=key == "price_level_id",
        )
    return None
