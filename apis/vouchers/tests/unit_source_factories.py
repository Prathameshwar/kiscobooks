"""Explicit signed base-unit evidence for voucher integration fixtures."""

from billing_platform.ids import uuid7


def unit_masters(item, unit):
    return (
        {
            "entity_type": "item",
            "source_id": str(item),
            "source_version": 1,
            "status": "ACTIVE",
            "facts": {"base_unit_id": str(unit)},
        },
        {
            "entity_type": "unit",
            "source_id": str(unit),
            "source_version": 1,
            "status": "ACTIVE",
            "facts": {"dimension": "COUNT", "decimal_places": 4, "quantity_increment": "0.0001"},
        },
        {
            "entity_type": "item_unit_revision",
            "source_id": str(uuid7()),
            "source_version": 1,
            "status": "ACTIVE",
            "facts": {
                "version": 1,
                "item_id": str(item),
                "unit_id": str(unit),
                "binding_id": str(uuid7()),
                "usage_role": "BASE",
                "conversion_mode": "FIXED",
                "numerator": "1",
                "denominator": "1",
                "quantity_decimal_places": 4,
                "quantity_increment": "0.0001",
                "fractional_entry": True,
                "valid_from": "2020-01-01",
                "valid_to": None,
            },
        },
    )
