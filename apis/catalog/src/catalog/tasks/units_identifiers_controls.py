"""Native authoring controls; immutable semantics remain enforced by commands."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

ENTITIES = {
    "catalog.unit_conversion",
    "catalog.pack_type",
    "catalog.identifier_type",
    "catalog.identifier_namespace",
    "catalog.identifier_profile",
    "catalog.identifier_profile_requirement",
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in ENTITIES:
        return None
    label = key.replace("_", " ").capitalize()
    if key == "code":
        return ConfigurationControl(
            kind="text",
            label="Code",
            max_length=40 if entity == "catalog.identifier_namespace" else 30,
        )
    if key == "name":
        return ConfigurationControl(
            kind="text",
            label="Name",
            max_length=120 if entity == "catalog.identifier_namespace" else 100,
        )
    if key in {"is_active", "is_barcode", "requires_slot"}:
        return ConfigurationControl(
            kind="boolean",
            label={
                "is_active": "Active",
                "is_barcode": "Barcode identifier",
                "requires_slot": "Require identifier slots",
            }[key],
        )
    if key in {"from_unit_id", "canonical_unit_id"}:
        return ConfigurationControl(
            kind="reference",
            label="Source unit" if key == "from_unit_id" else "Canonical unit",
            reference_source="units",
        )
    if key in {"numerator", "denominator"}:
        # Strings avoid JavaScript precision loss for native BIGINT ratio parts.
        return ConfigurationControl(kind="text", label=label, max_length=19)
    if entity == "catalog.identifier_profile_requirement":
        values = {
            "identifier_type": [("SERIAL", "Serial number"), ("IMEI", "IMEI")],
            "namespace_rule": [
                ("COMPANY", "Company"),
                ("MANUFACTURER_SKU", "Manufacturer and SKU"),
            ],
        }
        if key in values:
            return ConfigurationControl(
                kind="select",
                label=label,
                choices=[
                    ConfigurationChoice(value=value, label=title) for value, title in values[key]
                ],
            )
        if key in {"min_count", "max_count"}:
            return ConfigurationControl(
                kind="integer",
                label="Minimum count" if key == "min_count" else "Maximum count",
                minimum=0 if key == "min_count" else 1,
                maximum=8,
            )
    return None
