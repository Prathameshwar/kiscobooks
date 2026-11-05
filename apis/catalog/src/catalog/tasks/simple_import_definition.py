"""Simple import columns and business references resolve through native Catalog policy."""

import uuid
from typing import Any, Literal, cast

from billing_platform.authz import ScopePath
from billing_platform.bulk import selection_digest
from billing_platform.company_context import CompanyContext
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemGroup
from catalog.models.commercial import Brand, BrandSeries
from catalog.models.products import Item, ProductFamily
from catalog.models.tax import TaxClassification, TaxRule
from catalog.models.units import UnitOfMeasure
from catalog.schemas.configuration import AuthoringDefaultsQuery
from catalog.schemas.simple_product_creation import SimpleCreationInput, SimpleSalePrice
from catalog.schemas.simple_product_import import SimpleImportRow
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_authoring import suggestions
from catalog.tasks.field_context import load_field_context
from catalog.tasks.pricing_commands import business_date
from catalog.tasks.product_creation_review import configuration_fingerprint
from catalog.tasks.product_mode import read as product_mode
from catalog.tasks.simple_creation_preparation import UNSUPPORTED_SIMPLE_OPTIONS, default_group
from catalog.tasks.simple_sale_prices import sale_choices

DEFINITION = "simple_products"
RESOURCE = "simple_product_create"
FIELD_MAP = {
    "name": ("catalog.item", "name"),
    "code": ("catalog.item", "sku"),
    "kind": ("catalog.product_family", "kind"),
    "group": ("catalog.family_group_assignment", "group_id"),
    "base_unit": ("catalog.item", "base_unit_id"),
    "hsn_sac": ("catalog.catalog_tax_binding", "classification_id"),
    "gst_rule": ("catalog.catalog_tax_binding", "rule_id"),
    "purchase_price": ("catalog.item_price_draft", "amount"),
    "sale_price": ("catalog.item_price_draft", "amount"),
    "sale_prices": ("catalog.item_price_draft", "amount"),
    **{f"sale_price_{ordinal}": ("catalog.item_price_draft", "amount") for ordinal in range(1, 65)},
    "mrp": ("catalog.item_mrp", "amount"),
    "brand": ("catalog.product_family", "brand_id"),
    "brand_series": ("catalog.product_family", "series_id"),
    "model_code": ("catalog.product_family", "model_code"),
    "barcode_value": ("catalog.item_barcode", "value"),
    "barcode_symbology": ("catalog.item_barcode", "symbology"),
    # Retained creation requests use the nested input after source-file expiry.
    "barcode": ("catalog.item_barcode", "value"),
}


async def require_readable(
    db: AsyncSession, actor: Actor, company: uuid.UUID, fields: set[str]
) -> None:
    entities = {FIELD_MAP[key][0] for key in fields if key in FIELD_MAP}
    entities |= {"catalog.item", "catalog.product_family"}
    for entity in entities:
        context = await load_field_context(db, actor, company, entity)
        if set(context.native.fields) - context.readable() or any(
            "custom_field:" + field.key not in context.readable() for field in context.definitions
        ):
            raise PermissionDeniedError("Import contains protected product fields")
    if "purchase_price" in fields:
        actor.require_scope("purchase_price.read", target=ScopePath(company_id=company))


async def by_code(
    access: ConfigurationAccess, model: Any, code: str, field: str, **filters: Any
) -> uuid.UUID:
    context = await access.context(model)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("Import reference fields are protected")
    query = select(model.id).where(model.company_id == access.company, model.code == code)
    for key, value in filters.items():
        query = query.where(getattr(model, key) == value)
    if hasattr(model, "is_active"):
        query = query.where(model.is_active.is_(True))
    if model is TaxClassification:
        today = business_date(context.company.timezone)
        query = query.where(model.valid_from <= today, model.valid_to.is_(None))
    choices = list(await access.db.scalars(query.limit(2)))
    if len(choices) != 1:
        raise ValidationFailedError(
            "Choose an available reference code", fields={field: "Unknown or ambiguous code"}
        )
    await access.reference(model, choices[0])
    return cast(uuid.UUID, choices[0])


async def product_input(
    access: ConfigurationAccess, values: dict[str, Any], sale_levels: list[dict[str, Any]]
) -> SimpleCreationInput:
    values = dict(values)
    sale_prices = []
    for level in sale_levels:
        column = "sale_price_" + str(level["ordinal"])
        amount = values.pop(column, None)
        if amount is None or amount == "":
            continue
        try:
            sale_prices.append(
                SimpleSalePrice.model_validate(
                    {
                        "price_level_id": level["price_level_id"],
                        "amount": amount,
                    }
                )
            )
        except ValidationError as error:
            raise ValidationFailedError(
                "Review the selling price",
                fields={
                    column: "Enter an exact amount of zero or more with up to four decimal places"
                },
            ) from error
    row = SimpleImportRow.model_validate(values)
    data = row.model_dump(
        exclude_none=True,
        exclude={
            "group",
            "base_unit",
            "hsn_sac",
            "gst_rule",
            "brand",
            "brand_series",
            "barcode_value",
            "barcode_symbology",
        },
    )
    if sale_prices:
        data["sale_prices"] = sale_prices
    if row.barcode_symbology and not row.barcode_value:
        raise ValidationFailedError(
            "Barcode format needs a value", fields={"barcode_value": "Enter the barcode value"}
        )
    if row.barcode_value:
        data["barcode"] = {
            "value": row.barcode_value,
            "symbology": row.barcode_symbology or "CODE128",
        }
    data["base_unit_id"] = await by_code(access, UnitOfMeasure, row.base_unit, "base_unit")
    if row.group:
        data["group_id"] = await by_code(access, ItemGroup, row.group, "group")
    if row.brand:
        data["brand_id"] = await by_code(access, Brand, row.brand, "brand")
    if row.brand_series:
        if not row.brand:
            raise ValidationFailedError("Brand series needs a brand", fields={"brand": "Required"})
        data["series_id"] = await by_code(
            access, BrandSeries, row.brand_series, "brand_series", brand_id=data["brand_id"]
        )
    if row.hsn_sac or row.gst_rule:
        if not row.hsn_sac or not row.gst_rule:
            raise ValidationFailedError(
                "Complete GST details", fields={"hsn_sac": "Required", "gst_rule": "Required"}
            )
        data["tax"] = {
            "classification_id": await by_code(
                access, TaxClassification, row.hsn_sac, "hsn_sac", item_kind=row.kind
            ),
            "rule_id": await by_code(access, TaxRule, row.gst_rule, "gst_rule", item_kind=row.kind),
            "directions": ["SALE", "PURCHASE"],
        }
    return SimpleCreationInput.model_validate(data)


async def snapshot(
    db: AsyncSession,
    actor: Actor,
    context: CompanyContext,
    parameters: dict[str, str],
    opening_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    company = context.company_id
    if (
        set(parameters) - {"resource", "kind", "_configuration"}
        or parameters.get("resource", RESOURCE) != RESOURCE
    ):
        raise ValidationFailedError("Unsupported Simple import template options")
    kind = parameters.get("kind", "GOODS")
    if kind not in {"GOODS", "SERVICE"}:
        raise ValidationFailedError("Choose Goods or Services")
    mode = await product_mode(db, actor, company)
    if mode.product_family_sku_enabled:
        raise ConflictError("Use the product profile and SKU import for this company")
    access = ConfigurationAccess(db, actor, company)
    item_context = await access.context(Item)
    today = business_date(item_context.company.timezone)
    group = await default_group(access)
    defaults = await suggestions(
        access,
        AuthoringDefaultsQuery(
            as_of=today, kind=cast(Literal["GOODS", "SERVICE"], kind), group_id=group
        ),
    )
    configuration = defaults.configuration
    sale_levels = await sale_choices(access, configuration, today)
    unsupported = [
        option.replace("_", " ")
        for option in (*UNSUPPORTED_SIMPLE_OPTIONS, "category", "manufacturer")
        if getattr(configuration.options, option + "_mode") == "REQUIRED"
    ]
    if unsupported:
        raise ConflictError(
            "Simple import cannot capture required "
            + ", ".join(unsupported)
            + ". Review Product Configuration before importing."
        )
    signature = selection_digest(
        {
            "mode": mode.row_version,
            "configuration": configuration_fingerprint(configuration),
            "finance": context.finance.configuration_hash if context.finance else None,
            **(
                {"sale_price_levels": [level.model_dump(mode="json") for level in sale_levels]}
                if sale_levels
                else {}
            ),
        }
    )
    if parameters.get("_configuration") not in {None, signature}:
        raise ConflictError(
            "Product configuration changed; download a current template and review the file"
        )
    schema = SimpleImportRow.model_json_schema()
    properties = schema["properties"]
    required = set(schema.get("required", []))
    properties["kind"].update(enum=[kind], default=kind)
    gst = item_context.company.default_tax_system == "gst_in"
    for key in ("hsn_sac", "gst_rule"):
        if gst:
            required.add(key)
        else:
            properties.pop(key)
    for key, mode_value in (
        ("purchase_price", configuration.pricing.purchase_reference_mode),
        ("sale_price", configuration.pricing.sale_price_mode),
        ("mrp", configuration.pricing.mrp_mode if kind == "GOODS" else "DISABLED"),
        ("brand", configuration.options.brand_mode),
        ("model_code", configuration.options.model_mode),
        ("barcode_value", configuration.options.barcode_mode),
    ):
        if mode_value == "DISABLED":
            properties.pop(key, None)
        elif mode_value == "REQUIRED":
            required.add(key)
    if sale_levels:
        sale_schema = properties.pop("sale_price")
        required.discard("sale_price")
        for level in sale_levels:
            column = "sale_price_" + str(level.ordinal)
            properties[column] = dict(sale_schema) | {
                "title": level.name + " selling price",
                "description": ("Including" if level.tax_basis == "INCLUSIVE" else "Excluding")
                + " tax. Amount per base unit in "
                + context.base_currency
                + ".",
            }
            if level.required:
                required.add(column)
    if "brand" not in properties:
        properties.pop("brand_series")
    if "barcode_value" not in properties:
        properties.pop("barcode_symbology")
    capture = {field["key"]: field for field in opening_fields}
    opening = kind == "GOODS" and "inventory" in context.features and "purchase_price" in properties
    quantity = capture.get("quantity", {})
    if not opening or not (
        quantity.get("readable") and quantity.get("writable") and quantity.get("visible")
    ):
        properties.pop("opening_quantity")
        properties.pop("opening_date")
    elif context.finance:
        properties["opening_date"]["description"] = (
            "Blank uses "
            + str(context.finance.books_begin_date)
            + ". Any supplied date must match this books begin date."
        )
    for key, model in (("custom_fields", Item), ("shared_custom_fields", ProductFamily)):
        field_context = await access.context(model)
        custom = [
            definition.model_dump(mode="json")
            for definition in field_context.definitions
            if definition.is_active
        ]
        schema["x-custom-fields" if key == "custom_fields" else "x-shared-custom-fields"] = custom
        if not custom:
            properties.pop(key)
    await require_readable(db, actor, company, set(properties))
    schema["required"] = sorted(required)
    options = {}
    references: list[tuple[str, Any]] = [("base_unit", UnitOfMeasure), ("group", ItemGroup)]
    if "brand" in properties:
        references += [("brand", Brand), ("brand_series", BrandSeries)]
    if gst:
        references += [("hsn_sac", TaxClassification), ("gst_rule", TaxRule)]
    for key, reference_model in references:
        native = await access.context(reference_model)
        if set(native.native.fields) - native.readable():
            raise PermissionDeniedError("Import reference fields are protected")
        label = getattr(reference_model, "name", None)
        if label is None:
            label = reference_model.description
        query = select(reference_model.id, reference_model.code, label.label("name")).where(
            reference_model.company_id == company
        )
        if hasattr(reference_model, "is_active"):
            query = query.where(reference_model.is_active.is_(True))
        if hasattr(reference_model, "item_kind"):
            query = query.where(reference_model.item_kind == kind)
        if reference_model is TaxClassification:
            query = query.where(
                reference_model.valid_from <= today,
                reference_model.valid_to.is_(None),
            )
        rows = list(
            (
                await db.execute(
                    query.order_by(reference_model.code, reference_model.id).limit(201)
                )
            ).mappings()
        )
        options[key] = {
            "items": [
                {"id": str(row.id), "code": row.code, "name": row.name} for row in rows[:200]
            ],
            "truncated": len(rows) > 200,
        }
    return {
        "version": 1,
        "parameters": {"resource": RESOURCE, "kind": kind, "_configuration": signature},
        "tabular": {"resource": RESOURCE, "action": "CREATE", "defaults": {"kind": kind}},
        "result_fields": ["code", "name", "opening_posted"]
        + ["sale_price_" + str(level.ordinal) for level in sale_levels]
        + (["barcode_value", "barcode_symbology"] if "barcode_value" in properties else []),
        "result_headers": {"code": "product_code", "name": "product_name"},
        "completion_result_fields": ["opening_posted"],
        "schemas": {RESOURCE + ":CREATE": schema},
        "fields": {RESOURCE: []},
        "options": options,
        "sale_price_levels": [level.model_dump(mode="json") for level in sale_levels],
        "instructions": (
            "One product per row. Use reference codes from Import_Options. "
            "Blank product code is generated once; blank group uses Default. "
            "Prices and quantities are exact text. Validation saves no products. "
            "When multiple selling levels are enabled, use the named sale_price_N columns. "
            "When Barcode is enabled, enter its value as text to preserve leading zeroes. "
            "Blank barcode format uses CODE128; GTIN and QR are also supported. "
            "Import activates each product and posts Goods opening stock automatically. "
            "Opening value is Purchase price multiplied by Opening quantity. "
            "Services have no opening stock. Correct validation errors before Import; "
            "pending work resumes using the original row identity. "
            "Option sheets show up to 200 active codes per reference; other existing "
            "company codes may also be entered."
        ),
        "product_configuration": {
            "as_of": str(today),
            "kind": kind,
            "options": [],
            "inventory_profile": opening,
            "note": (
                "Imported products become active and ready. Any opening stock is posted "
                "automatically before a row is reported ready."
            ),
        },
    }
