"""Typed editor hints for existing native configuration fields, never authority."""

from typing import Literal, get_args

from catalog.domain.pricing_dimensions import PRICING_DIMENSIONS
from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl
from catalog.schemas.units import Dimension
from catalog.tasks.attribute_controls import control as attribute_control
from catalog.tasks.bom_controls import control as bom_control
from catalog.tasks.definition_controls import control as definition_control
from catalog.tasks.pricing_controls import control as pricing_control
from catalog.tasks.product_classification_controls import control as product_classification_control
from catalog.tasks.product_profile_controls import control as product_profile_control
from catalog.tasks.promotion_stack_controls import control as stack_control
from catalog.tasks.tax_controls import control as tax_control
from catalog.tasks.units_identifiers_controls import control as units_identifiers_control
from catalog.tasks.warehouse_structure_controls import control as warehouse_control

REQUIREMENTS = [
    ("INHERIT", "Use system default"),
    ("DISABLED", "Disabled"),
    ("OPTIONAL", "Optional"),
    ("REQUIRED", "Required"),
]
PROFILE_MODES = [
    ("INHERIT", "Use system default"),
    ("CLEAR", "Clear default"),
    ("VALUE", "Choose a reference"),
]
SCOPES = [
    ("COMPANY", "Company"),
]
PROFILES: dict[str, tuple[str, str, Literal["GOODS", "SERVICE"] | None]] = {
    "goods_type_revision": ("Goods product type", "product-type-revisions", "GOODS"),
    "service_type_revision": ("Service product type", "product-type-revisions", "SERVICE"),
    "inventory_template_revision": ("Inventory profile", "inventory-template-revisions", None),
    "warranty_revision": ("Warranty profile", "warranty-revisions", None),
    "return_policy_revision": ("Return policy", "return-policy-revisions", None),
    "handling_revision": ("Handling profile", "handling-revisions", None),
    "identifier_profile": ("Identifier profile", "identifier-profiles", None),
}

UNIT_OPTIONS = frozenset({"alternate_units", "compound_units", "measured_units"})
ENTRY_LABELS = {
    "alternate_units": "Alternate units and fixed conversion",
    "compound_units": "Compound quantities",
    "measured_units": "Measured conversion",
    "model": "Model",
}
ENTRY_HELP = {
    "brand_mode": "Allow a product brand and its optional brand series.",
    "model_mode": "Allow the existing model code on a product. Model does not require a brand.",
    "alternate_units_mode": (
        "Allow another unit or pack with a fixed conversion, such as 1 box = 12 pieces. "
        "Base-unit entry is always available."
    ),
    "compound_units_mode": (
        "Allow a quantity entered in multiple components, such as 2 boxes and 3 pieces."
    ),
    "measured_units_mode": (
        "Allow conversions measured for each transaction, such as the actual weight of a pack. "
        "Applies to goods; another unit also requires alternate units."
    ),
}


PRICING_HELP = {
    "multiple_price_levels_mode": (
        "Allow selling-price levels beyond PRICE1, such as retail and wholesale. "
        "Requires the multiple price levels company capability."
    ),
    "unit_prices_mode": (
        "Allow separate prices for an alternate unit or pack. Disabled keeps explicit prices "
        "in the product's base unit; unit conversion policy is separate."
    ),
    "quantity_tiers_mode": (
        "Allow quantity slabs with different prices. Disabled keeps one amount per price record."
    ),
    "channel_prices_mode": (
        "Allow a different price for each sales channel, such as retail or online."
    ),
    "additional_currencies_mode": (
        "Allow prices in currencies other than the company currency. Requires the "
        "multi-currency company capability; this does not convert prices."
    ),
    "formula_prices_mode": (
        "Allow price formulas using reference costs or MRP. Disabled uses entered amounts."
    ),
    "sale_level_count": (
        "Number of selling-price levels to check when sale prices are required. "
        "This does not enable additional levels."
    ),
}


def choices(values: list[tuple[str, str]]) -> list[ConfigurationChoice]:
    return [ConfigurationChoice(value=value, label=label) for value, label in values]


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity == "catalog.company_product_authoring_configuration":
        if key == "product_family_sku_enabled":
            return ConfigurationControl(kind="boolean", label="Enable product families and SKUs")
        if key == "change_reason":
            return ConfigurationControl(kind="text", label="Change reason", max_length=250)
    definition = definition_control(entity, key)
    if definition is not None:
        return definition
    stack = stack_control(entity, key)
    if stack is not None:
        return stack
    bom = bom_control(entity, key)
    if bom is not None:
        return bom
    classification = product_classification_control(entity, key)
    if classification is not None:
        return classification
    profile = product_profile_control(entity, key)
    if profile is not None:
        return profile
    pricing = pricing_control(entity, key)
    if pricing is not None:
        return pricing
    attribute = attribute_control(entity, key)
    if attribute is not None:
        return attribute
    units = units_identifiers_control(entity, key)
    if units is not None:
        return units
    warehouse = warehouse_control(entity, key)
    if warehouse is not None:
        return warehouse
    tax = tax_control(entity, key)
    if tax is not None:
        return tax
    label = key.replace("_", " ").capitalize()
    if entity == "catalog.product_configuration_scope":
        if key == "scope_kind":
            return ConfigurationControl(
                kind="select", label="Configuration applies to", choices=choices(SCOPES)
            )
        # Ownership columns are retained as provenance, never new authoring controls.
        if key in {"product_type_id", "group_id", "family_id", "item_id"}:
            return None
    if entity == "catalog.product_configuration_draft":
        if key == "effective_from":
            return ConfigurationControl(kind="date", label="Effective from")
        if key == "change_reason":
            return ConfigurationControl(kind="text", label="Reason for change", max_length=250)
    if entity in {"catalog.product_entry_option_policy", "catalog.product_pricing_policy"}:
        if entity == "catalog.product_pricing_policy" and key in PRICING_DIMENSIONS:
            return ConfigurationControl(
                kind="select",
                label=PRICING_DIMENSIONS[key],
                choices=choices(
                    [
                        ("INHERIT", "Use system default"),
                        ("DISABLED", "Disabled"),
                        ("ENABLED", "Enabled"),
                    ]
                ),
            )
        if key.endswith("_mode"):
            return ConfigurationControl(
                kind="select",
                label=ENTRY_LABELS.get(key.removesuffix("_mode"), label.removesuffix(" mode"))
                if entity == "catalog.product_entry_option_policy"
                else label.removesuffix(" mode"),
                choices=choices(REQUIREMENTS),
            )
        if key.endswith("_default"):
            return ConfigurationControl(
                kind="boolean",
                label="Enable " + label.removesuffix(" default").lower() + " by default",
                nullable=True,
                depends_on=key.removesuffix("_default") + "_mode",
                show_when="OPTIONAL",
            )
        if key == "sale_level_count":
            return ConfigurationControl(
                kind="integer",
                label="Number of sale price levels",
                nullable=True,
                minimum=1,
                maximum=64,
            )
    if entity == "catalog.catalog_default_profile":
        for prefix, (title, source, kind) in PROFILES.items():
            if key == prefix + "_mode":
                return ConfigurationControl(
                    kind="select", label=title + " default", choices=choices(PROFILE_MODES)
                )
            if key == prefix + "_id":
                return ConfigurationControl(
                    kind="reference",
                    label=title,
                    nullable=True,
                    reference_source=source,
                    reference_kind=kind,
                    depends_on=prefix + "_mode",
                    show_when="VALUE",
                )
    if entity == "catalog.product_numeric_default":
        if key == "dimension":
            return ConfigurationControl(
                kind="select",
                label="Unit dimension",
                # Python 3.12's `type Dimension = Literal[...]` wraps the Literal.
                choices=choices(
                    [
                        (value, value.capitalize())
                        for value in get_args(getattr(Dimension, "__value__", Dimension))
                    ]
                ),
            )
        if key.endswith("_decimal_places"):
            return ConfigurationControl(
                kind="integer", label=label, nullable=True, minimum=0, maximum=4
            )
        if key in {"quantity_increment", "price_increment", "price_basis_quantity"}:
            return ConfigurationControl(kind="decimal", label=label, nullable=True)
        if key == "currency":
            return ConfigurationControl(
                kind="reference",
                label="Price currency",
                nullable=True,
                reference_source="currencies",
            )
    return None
