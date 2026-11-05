"""Native BOM editor hints; field policies and company capability remain authoritative."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

ENTITIES = frozenset(
    "catalog." + name
    for name in (
        "bom",
        "bom_draft",
        "bom_revision",
        "bom_component",
        "bom_output",
        "bom_assignment",
    )
)
PUBLISH_PERMISSIONS = {
    entity: "bom.publish" for entity in ENTITIES - {"catalog.bom", "catalog.bom_assignment"}
}
CHOICES = {
    "basis": (("GROSS_INPUT", "Gross input"), ("NET_REQUIRED", "Net requirement")),
    "timing": (("PER_BASIS", "Per output basis"), ("PER_RUN", "Fixed per run")),
    "role": (
        ("PRIMARY", "Primary output"),
        ("CO_PRODUCT", "Co-product"),
        ("BY_PRODUCT", "By-product"),
        ("SCRAP", "Scrap"),
    ),
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in ENTITIES:
        return None
    label = {
        "item_id": "Goods SKU",
        "unit_revision_id": "Pinned SKU unit",
        "route_revision_id": "Manufacturing route",
        "route_step_id": "Route step",
        "bom_revision_id": "Published recipe",
        "warehouse_id": "Production warehouse",
        "valid_from": "Applies from",
        "valid_to": "Applies through",
        "quantity": "Input quantity",
        "nominal_quantity": "Nominal output quantity",
        "loss_fraction": "Loss fraction (0 to less than 1)",
        "yield_fraction": "Yield fraction (greater than 0 to 1)",
        "basis": "Quantity basis",
        "timing": "Input timing",
        "role": "Output role",
    }.get(key, key.replace("_", " ").capitalize())
    if key in CHOICES:
        return ConfigurationControl(
            kind="select",
            label=label,
            choices=[ConfigurationChoice(value=value, label=text) for value, text in CHOICES[key]],
        )
    if key in {
        "quantity",
        "nominal_quantity",
        "loss_fraction",
        "yield_fraction",
        "batch_minimum",
        "batch_maximum",
        "batch_multiple",
    }:
        return ConfigurationControl(
            kind="decimal", label=label, nullable=key.startswith("batch_"), max_length=25
        )
    if key in {"definition_date", "valid_from", "valid_to"}:
        return ConfigurationControl(kind="date", label=label, nullable=key == "valid_to")
    if key in {"is_active"}:
        return ConfigurationControl(kind="boolean", label=label)
    if key in {"code", "name", "specification", "change_reason"}:
        return ConfigurationControl(
            kind="text",
            label=label,
            max_length={
                "code": 30,
                "name": 100,
                "specification": 2000,
                "change_reason": 500,
            }[key],
        )
    if key == "sequence":
        return ConfigurationControl(
            kind="integer",
            label=label,
            minimum=1,
            maximum=1000 if entity == "catalog.bom_component" else 100,
        )
    if key.endswith("_id"):
        source = {
            "item_id": "bom-goods",
            "unit_revision_id": "bom-unit-revisions",
            "route_revision_id": "bom-route-revisions",
            "route_step_id": "bom-route-steps",
            "warehouse_id": "warehouses",
            "bom_revision_id": "bom-revisions",
        }.get(key)
        if source:
            return ConfigurationControl(
                kind="reference",
                label=label,
                reference_source=source,
                nullable=key
                in {"unit_revision_id", "route_revision_id", "route_step_id", "warehouse_id"},
            )
    return None
