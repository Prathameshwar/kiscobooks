"""Import presentation and derived creation guards use native effective settings."""

import uuid
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.products import Item, ProductFamily
from catalog.schemas.configuration import EffectiveConfiguration, EffectiveQuery
from catalog.tasks.configuration_resolution import resolve
from catalog.tasks.field_context import load_field_context
from catalog.tasks.product_creation_review import configuration_fingerprint

OPTIONS = {
    "brand": "Brands",
    "model": "Model codes",
    "barcode": "Barcodes",
    "category": "Categories",
    "manufacturer": "Manufacturers",
    "variants": "Variant SKUs",
    "alternate_units": "Alternate units",
    "compound_units": "Compound quantities",
    "measured_units": "Measured units",
}
DERIVED = {
    "expected_version",
    "expected_generation",
    "expected_source_version",
    "configuration_fingerprint",
    "authoring_version",
    "revision",
    "accept_defaults",
}


async def configuration(
    db: AsyncSession, actor: Actor, company: uuid.UUID, values: dict[str, Any]
) -> EffectiveConfiguration:
    context = await load_field_context(db, actor, company, "catalog.product_configuration_scope")
    try:
        query = EffectiveQuery.model_validate(
            {
                "as_of": values.get("as_of")
                or utcnow().astimezone(ZoneInfo(context.company.timezone)).date(),
                "kind": values.get("kind", "GOODS"),
                "product_type_revision_id": values.get("product_type_revision_id") or None,
                "group_id": values.get("group_id") or None,
                "item_id": values.get("item_id"),
                "family_id": values.get("family_id"),
            }
        )
    except (ValidationError, ValueError) as error:
        raise ValidationFailedError(
            "Choose a valid product kind, date, published type and group."
        ) from error
    return await resolve(db, actor, company, query)


def guide(config: EffectiveConfiguration, *, advanced: bool) -> dict[str, Any]:
    return {
        "as_of": str(config.as_of),
        "kind": config.kind,
        "options": [
            {
                "key": key,
                "label": label,
                "mode": "DISABLED"
                if key == "variants" and not advanced
                else getattr(config.options, key + "_mode"),
            }
            for key, label in OPTIONS.items()
        ],
        "inventory_profile": config.profiles.inventory_template_revision_id is not None,
        "note": (
            "Required options must be completed before activation. Each row is checked against "
            "its own type, group and effective date. Product creation rows save drafts; "
            "batches, serials and opening stock use their normal workflows."
        ),
    }


def template_schema(
    schema: dict[str, Any],
    config: EffectiveConfiguration | None,
    action: str,
    parameters: dict[str, str],
    *,
    simple: bool = False,
) -> None:
    # These values are derived/reviewed by the import owner, never copied from a sheet.
    for definition in [schema, *schema.get("$defs", {}).values()]:
        for key in DERIVED:
            definition.get("properties", {}).pop(key, None)
        if "required" in definition:
            definition["required"] = [key for key in definition["required"] if key not in DERIVED]
    if action != "CREATE" or config is None:
        return
    schema["properties"]["kind"]["enum"] = [config.kind]
    if parameters.get("product_type_revision_id"):
        schema["properties"]["product_type_revision_id"]["enum"] = [
            parameters["product_type_revision_id"]
        ]
    for option, fields in {"brand": ("brand_id", "series_id"), "model": ("model_code",)}.items():
        if getattr(config.options, option + "_mode") != "DISABLED":
            continue
        for field in fields:
            if field in schema.get("required", []):
                raise ValidationFailedError(
                    f"A required {option} field conflicts with disabled product configuration. "
                    "Review field and product settings."
                )
            schema["properties"].pop(field, None)
            schema["required"] = [key for key in schema.get("required", []) if key != field]
    if config.options.barcode_mode == "DISABLED":
        schema.get("$defs", {}).get("InitialProductSetup", {}).get("properties", {}).pop(
            "barcodes", None
        )
    for definition in schema.get("$defs", {}).values():
        props = definition.get("properties", {})
        if "is_axis" in props and (simple or config.options.variants_mode == "DISABLED"):
            props["is_axis"]["enum"] = [False]
    unit = schema.get("$defs", {}).get("UnitBindingInput", {}).get("properties", {})
    if config.options.measured_units_mode == "DISABLED":
        if "conversion_mode" in unit:
            unit["conversion_mode"]["enum"] = ["FIXED"]
        if "role" in unit:
            unit["role"]["enum"] = [role for role in unit["role"]["enum"] if role != "MEASURED"]
    if config.options.alternate_units_mode == "DISABLED" and "role" in unit:
        unit["role"]["enum"] = [role for role in unit["role"]["enum"] if role != "PACK"]


async def creation_data(
    db: AsyncSession, actor: Actor, company: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    setup = data.get("initial_setup")
    values = setup if isinstance(setup, dict) else {}
    if data.get("kind") not in {"GOODS", "SERVICE"} or not data.get("product_type_revision_id"):
        return data  # The native schema reports missing/invalid required fields.
    config = await configuration(
        db,
        actor,
        company,
        {
            "kind": data["kind"],
            "product_type_revision_id": data["product_type_revision_id"],
            "as_of": values.get("effective_from"),
            "group_id": values.get("group_id"),
        },
    )
    if config.options.brand_mode == "DISABLED" and (data.get("brand_id") or data.get("series_id")):
        raise ValidationFailedError(
            "Brand assignment is disabled for this product.",
            fields={"brand_id": "Disabled by product configuration."},
        )
    if config.options.barcode_mode == "DISABLED" and values.get("barcodes"):
        raise ValidationFailedError(
            "Barcodes are disabled for this product.",
            fields={"initial_setup.barcodes": "Disabled by product configuration."},
        )
    if config.options.model_mode == "DISABLED" and data.get("model_code"):
        raise ValidationFailedError(
            "Model assignment is disabled for this product.",
            fields={"model_code": "Disabled by product configuration."},
        )
    if not isinstance(setup, dict):
        return data
    derived = dict(setup)
    derived.setdefault("expected_generation", config.policy_generation)
    derived.setdefault("expected_source_version", config.source_version)
    derived.setdefault("configuration_fingerprint", configuration_fingerprint(config))
    for key in ("units", "barcodes"):
        entries = derived.get(key)
        if isinstance(entries, list):
            derived[key] = [
                {"expected_version": 1, **entry} if isinstance(entry, dict) else entry
                for entry in entries
            ]
    if isinstance(derived.get("attributes"), dict):
        derived["attributes"] = {"expected_version": 1, **derived["attributes"]}
    return {**data, "initial_setup": derived}


async def update_options(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    resource: str,
    target: uuid.UUID,
    data: dict[str, Any],
) -> None:
    incoming = {key: data[key] for key in ("brand_id", "series_id", "model_code") if data.get(key)}
    if not incoming:
        return
    item = (
        await company_object(db, Item, target, company_id=company)
        if resource == "simple_product"
        else None
    )
    family = await company_object(
        db, ProductFamily, item.family_id if item else target, company_id=company
    )
    config = await configuration(
        db,
        actor,
        company,
        {
            "kind": family.kind,
            "item_id": item.id if item else None,
            "family_id": family.id,
        },
    )
    if config.options.brand_mode == "DISABLED" and any(
        str(value) != str(getattr(family, key))
        for key, value in incoming.items()
        if key in {"brand_id", "series_id"}
    ):
        raise ValidationFailedError(
            "Brand assignment is disabled for this product.",
            fields={"brand_id": "Disabled by product configuration."},
        )
    if config.options.model_mode == "DISABLED" and incoming.get("model_code") not in {
        None,
        family.model_code,
    }:
        raise ValidationFailedError(
            "Model assignment is disabled for this product.",
            fields={"model_code": "Disabled by product configuration."},
        )
