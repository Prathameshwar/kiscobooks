"""Presentation hints for native tax inputs; commands retain all authority."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

TAX_ENTITIES = {
    "catalog.tax_category",
    "catalog.tax_classification",
    "catalog.tax_rule",
    "catalog.tax_rate_series",
    "catalog.tax_rate",
    "catalog.tax_rate_component",
    "catalog.tax_rule_applicability",
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in TAX_ENTITIES:
        return None
    label = key.replace("_", " ").capitalize()
    selections = {
        "code_system": [("HSN", "HSN (goods)"), ("SAC", "SAC (services)")],
        "item_kind": [("GOODS", "Goods"), ("SERVICE", "Services")],
        "classification_scope": [
            ("SPECIFIC", "Specific HSN/SAC codes"),
            ("ANY", "Generic rate template"),
        ],
        "treatment": [
            ("TAXABLE", "Taxable"),
            ("NIL_RATED", "Nil rated"),
            ("EXEMPT", "Exempt"),
            ("NON_GST", "Outside GST"),
        ],
        "applicability": [
            ("INTRA_STATE", "Within a state"),
            ("INTRA_UT", "Within a union territory"),
            ("INTER_STATE", "Between states / territories"),
        ],
        "component": [(value, value) for value in ("CGST", "SGST", "UTGST", "IGST", "CESS")],
        "kind": [("PERCENT", "Percentage"), ("FIXED_PER_UNIT", "Fixed cess per unit")],
        "rounding_mode": [("HALF_UP", "Half up"), ("UP", "Round up"), ("DOWN", "Round down")],
        "match_kind": [("EXACT", "Exact code"), ("PREFIX", "Code prefix")],
    }
    if key in selections:
        return ConfigurationControl(
            kind="select",
            label=label,
            choices=[
                ConfigurationChoice(value=value, label=title) for value, title in selections[key]
            ],
        )
    references = {
        "tax_category_id": "tax-categories",
        "rule_id": "tax-rules",
        "series_id": "tax-rate-series",
        "unit_id": "units",
    }
    if key in references:
        return ConfigurationControl(
            kind="reference",
            label={
                "tax_category_id": "Tax category",
                "rule_id": "Tax rule",
                "series_id": "Rate series",
                "unit_id": "Unit",
            }[key],
            reference_source=references[key],
            nullable=key == "unit_id",
        )
    if key in {"valid_from", "valid_to"}:
        return ConfigurationControl(
            kind="date",
            label="Effective from" if key == "valid_from" else "Effective through",
            nullable=key == "valid_to",
        )
    if key == "is_active":
        return ConfigurationControl(kind="boolean", label="Active")
    if key == "position":
        return ConfigurationControl(kind="integer", label="Position", minimum=0, maximum=15)
    if key in {"percentage", "amount", "basis_quantity"}:
        return ConfigurationControl(kind="decimal", label=label, nullable=True)
    sizes = {
        "code": 8 if entity == "catalog.tax_classification" else 30,
        "name": 100,
        "description": 1000,
        "source_reference": 500,
        "source_url": 1000,
        "source_sha256": 64,
        "component_key": 30,
        "currency": 3,
    }
    if key in sizes:
        return ConfigurationControl(
            kind="text",
            label={
                "source_reference": "Official source reference",
                "source_url": "Official document URL",
                "source_sha256": "Document SHA-256",
            }.get(key, label),
            max_length=sizes[key],
            nullable=key == "currency",
        )
    return None
