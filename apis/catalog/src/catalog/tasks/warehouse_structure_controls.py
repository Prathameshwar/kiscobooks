"""Presentation hints for warehouse structure; native commands remain authoritative."""

from catalog.schemas.field_metadata import ConfigurationControl


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in {
        "catalog.warehouse_group",
        "catalog.warehouse_bin",
        "catalog.warehouse_group_parent",
        "catalog.warehouse_group_assignment",
    }:
        return None
    if key in {"code", "name"}:
        return ConfigurationControl(
            kind="text", label=key.capitalize(), max_length=30 if key == "code" else 100
        )
    if key == "is_active":
        return ConfigurationControl(kind="boolean", label="Active")
    if key in {"valid_from", "valid_to"}:
        return ConfigurationControl(
            kind="date",
            label="Effective from" if key == "valid_from" else "Effective through",
            nullable=key == "valid_to",
        )
    if key in {"warehouse_id", "group_id", "parent_group_id"}:
        return ConfigurationControl(
            kind="reference",
            label={
                "warehouse_id": "Warehouse",
                "group_id": "Warehouse group",
                "parent_group_id": "Parent group",
            }[key],
            reference_source="warehouses" if key == "warehouse_id" else "warehouse-groups",
            nullable=key == "parent_group_id",
        )
    return None
