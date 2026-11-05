"""Closed presentation hints for native product and classification authoring."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

ENTITIES = {
    "product_family",
    "item",
    "product_type",
    "product_type_revision",
    "category_scheme",
    "item_category",
    "brand",
    "brand_series",
    "manufacturer_site",
    "family_category",
    "family_group_assignment",
    "family_manufacturer",
    "item_unit_binding",
    "item_unit_revision",
    "item_barcode",
}
REFERENCES = {
    "product_type_revision_id": ("Published product type", "product-type-revisions"),
    "base_unit_id": ("Base unit", "units"),
    "unit_id": ("Unit", "units"),
    "brand_id": ("Brand", "brands"),
    "series_id": ("Brand series", "brand-series"),
    "parent_brand_id": ("Parent brand", "brands"),
    "owner_party_id": ("Owner party", "parties"),
    "manufacturer_id": ("Manufacturer", "manufacturers"),
    "site_id": ("Manufacturer site", "manufacturer-sites"),
    "scheme_id": ("Category scheme", "category-schemes"),
    "parent_id": ("Parent category", "item-categories"),
    "category_id": ("Category", "item-categories"),
    "group_id": ("Item group", "item-groups"),
    "attribute_set_revision_id": ("Attribute template", "attribute-set-revisions"),
    "inventory_template_revision_id": ("Inventory profile", "inventory-template-revisions"),
    "warranty_revision_id": ("Warranty profile", "warranty-revisions"),
    "return_policy_revision_id": ("Return profile", "return-policy-revisions"),
    "handling_revision_id": ("Handling profile", "handling-revisions"),
    "pack_type_id": ("Pack type", "pack-types"),
    "binding_id": ("Unit binding", "unit-bindings"),
    "secondary_unit_id": ("Secondary unit", "units"),
}
SETS = {
    "inventory_modes": ["NON_STOCK", "STOCK"],
    "tracking_modes": ["NONE", "BATCH", "SERIAL", "BATCH_SERIAL"],
    "unit_dimensions": ["COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"],
}
OPTIONS = {
    **SETS,
    "kind": ["GOODS", "SERVICE", "BOTH"],
    "membership_mode": ["SINGLE", "MULTIPLE"],
    "usage_role": ["BASE", "SALE", "PURCHASE", "BOTH", "PACK", "MEASURED"],
    "production_role": ["MANUFACTURER", "ASSEMBLER", "IMPORTER"],
    "conversion_mode": ["FIXED", "MEASURED"],
    "symbology": ["GTIN", "CODE128", "QR"],
}
BOOLEAN = {
    "is_active",
    "is_required",
    "is_primary",
    "sellable",
    "purchasable",
    "allow_variants",
    "require_brand",
    "require_manufacturer",
    "require_expiry",
    "fractional_entry",
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity.removeprefix("catalog.") not in ENTITIES:
        return None
    label = key.replace("_", " ").capitalize()
    if key in REFERENCES:
        label, source = REFERENCES[key]
        required = key in {
            "product_type_revision_id",
            "base_unit_id",
            "unit_id",
            "scheme_id",
            "category_id",
            "group_id",
        }
        required |= key == "brand_id" and entity == "catalog.brand_series"
        required |= key == "manufacturer_id" and entity in {
            "catalog.manufacturer_site",
            "catalog.family_manufacturer",
        }
        return ConfigurationControl(
            kind="reference", label=label, reference_source=source, nullable=not required
        )
    if key in OPTIONS:
        values = OPTIONS[key]
        if entity == "catalog.product_family" and key == "kind":
            values = ["GOODS", "SERVICE"]
        return ConfigurationControl(
            kind="select",
            label=label,
            choices=[
                ConfigurationChoice(value=value, label=value.replace("_", " ").title())
                for value in values
            ],
        )
    if key in BOOLEAN:
        return ConfigurationControl(kind="boolean", label=label)
    if key in {"valid_from", "valid_to"}:
        return ConfigurationControl(kind="date", label=label, nullable=key == "valid_to")
    if key == "quantity_decimal_places":
        return ConfigurationControl(
            kind="integer", label="Quantity decimal places", minimum=0, maximum=4
        )
    if key in {"quantity_increment", "nominal_ratio", "min_sale_quantity"}:
        return ConfigurationControl(
            kind="decimal", label=label, nullable=key != "quantity_increment", max_length=20
        )
    lengths = {
        "code": 30,
        "sku": 30,
        "name": 100,
        "description": 2000,
        "model_code": 100,
        "country_code": 2,
        "state_code": 6,
        "numerator": 19,
        "denominator": 19,
        "value": 128,
    }
    if key in lengths:
        return ConfigurationControl(
            kind="text",
            label={"sku": "SKU code", "country_code": "Country", "state_code": "State"}.get(
                key, label
            ),
            max_length=lengths[key],
            nullable=key in {"description", "model_code", "state_code", "numerator", "denominator"},
        )
    return None
