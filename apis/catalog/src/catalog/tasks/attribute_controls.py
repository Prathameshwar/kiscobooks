"""Native attribute controls; command rules remain the authority."""

from typing import get_args

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl
from catalog.schemas.units import Dimension

ENTITIES = {
    "catalog.attribute_definition",
    "catalog.attribute_option",
    "catalog.attribute_set",
    "catalog.attribute_set_revision",
    "catalog.attribute_set_member",
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in ENTITIES:
        return None
    label = key.replace("_", " ").capitalize()
    if key in {"code", "name", "value_text", "value_integer", "value_decimal"}:
        return ConfigurationControl(
            kind="text",
            label={
                "value_text": "Text value",
                "value_integer": "Whole number value",
                "value_decimal": "Decimal value",
            }.get(key, label),
            max_length={
                "code": 30,
                "name": 100,
                "value_text": 200,
                "value_integer": 20,
                "value_decimal": 21,
            }[key],
            nullable=key.startswith("value_"),
        )
    if key in {
        "is_active",
        "is_variant_capable",
        "value_boolean",
        "is_required",
        "allow_variant_axis",
    }:
        return ConfigurationControl(
            kind="boolean",
            label={
                "is_variant_capable": "May distinguish variants",
                "value_boolean": "Boolean value",
                "allow_variant_axis": "Allow variant axis",
            }.get(key, label),
            nullable=key == "value_boolean",
        )
    if key in {"value_type", "measurement_dimension"}:
        values = (
            ["TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE"]
            if key == "value_type"
            else list(get_args(getattr(Dimension, "__value__", Dimension)))
        )
        return ConfigurationControl(
            kind="select",
            label=label,
            nullable=key == "measurement_dimension",
            choices=[
                ConfigurationChoice(value=value, label=value.capitalize()) for value in values
            ],
        )
    if key in {"definition_id", "unit_id"}:
        return ConfigurationControl(
            kind="reference",
            label="Definition" if key == "definition_id" else "Measurement unit",
            reference_source="attribute-definitions" if key == "definition_id" else "units",
            nullable=key == "unit_id",
        )
    if key == "value_date":
        return ConfigurationControl(kind="date", label="Date value", nullable=True)
    if key == "position":
        return ConfigurationControl(kind="integer", label="Position", minimum=0, maximum=127)
    return None
