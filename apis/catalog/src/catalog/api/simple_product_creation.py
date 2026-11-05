"""One Save starts and resumes product setup using fresh actor authority."""

import uuid
from typing import Annotated, Literal

from billing_platform.authz import ScopePath
from billing_platform.company_context import CompanyContext, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    ErrorEnvelope,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select

from catalog.api.auth import actor
from catalog.api.field_metadata import field_set
from catalog.api.simple_products import product_field_set, secret
from catalog.api.units import no_query, unique_query
from catalog.models.projections import CompanyProjection
from catalog.schemas.configuration import AuthoringDefaultsQuery
from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl, FieldMetadata
from catalog.schemas.simple_product_creation import (
    SimpleBatchOptions,
    SimpleCreationInput,
    SimpleCreationOptions,
    SimpleCreationRevision,
    SimpleCreationStatus,
)
from catalog.tasks import simple_product_creation as tasks
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_authoring import suggestions
from catalog.tasks.pricing_commands import business_date
from catalog.tasks.product_stock_choice import available
from catalog.tasks.simple_classification_details import required_schemes
from catalog.tasks.simple_creation_preparation import default_group
from catalog.tasks.simple_creation_transport import CreationOwners
from catalog.tasks.simple_sale_prices import sale_choices
from catalog.tasks.simple_serial_preparation import serial_options

Idempotency = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/v1/companies/{company_id}/simple-product-creations",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
    dependencies=[Depends(unique_query), Depends(no_store)],
)


def context(request: Request, company: uuid.UUID, current: Actor) -> CompanyContext:
    token, signature = (
        request.headers.get("x-company-context"),
        request.headers.get("x-company-signature"),
    )
    if not token or not signature:
        raise AuthenticationRequiredError("Fresh company context is required for product creation")
    value = verify_company_context(token, signature, secret(request))
    value.assert_current(current, company)
    return value


def owners(request: Request) -> CreationOwners:
    return CreationOwners(
        request.app, request.headers, request.app.state.settings.simple_creation_origins
    )


def limit(request: Request, current: Actor, company: uuid.UUID) -> None:
    if not request.app.state.pricing_limiter.allow(
        f"simple:{current.tenant_id}:{company}:{current.user_id}", limit=120
    ):
        raise HTTPException(status_code=429, detail="product creation rate exceeded")


@router.get(
    "/options", response_model=SimpleCreationOptions, operation_id="get_simple_creation_options"
)
async def options(
    company_id: uuid.UUID,
    request: Request,
    kind: Literal["GOODS", "SERVICE"] = "GOODS",
    group_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
) -> SimpleCreationOptions:
    if set(request.query_params) - {"kind", "group_id"}:
        raise ValidationFailedError("Unknown product options query parameter")
    current.require_scope("item.create", target=ScopePath(company_id=company_id))
    facts = context(request, company_id, current)
    if facts.finance is None:
        raise ConflictError("Complete company financial setup before creating products")
    metadata_request = Request(dict(request.scope) | {"query_string": b""})
    fields: list[FieldMetadata] = []
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            profile = await db.scalar(
                select(CompanyProjection).where(CompanyProjection.company_id == company_id)
            )
            if profile is None:
                raise ConflictError("Company product defaults are still being prepared")
            today = business_date(profile.timezone)
            access = ConfigurationAccess(db, current, company_id)
            group = group_id or await default_group(access)
            defaults = await suggestions(
                access, AuthoringDefaultsQuery(as_of=today, kind=kind, group_id=group)
            )
            configuration = defaults.configuration
            batch = await available(access, configuration, defaults.product_type_revision_id, kind)
            serial = await serial_options(access, configuration, kind)
            sale_levels = await sale_choices(access, configuration, today)
            category_schemes = (
                await required_schemes(access)
                if configuration.options.category_mode != "DISABLED"
                else []
            )
            basic = await product_field_set(
                company_id, metadata_request, "create", None, current, db
            )
            fields.extend(basic.fields)
            mappings = [("family_group_assignment", "group_id", "group_id", "Product group")]
            if batch["available"]:
                mappings.append(
                    ("item_stock_choice", "batch_enabled", "batch_enabled", "Allow batch")
                )
            if configuration.options.category_mode != "DISABLED":
                mappings += [
                    ("family_category", "scheme_id", "category_scheme_id", "Category scheme"),
                    ("family_category", "category_id", "category_id", "Category"),
                    ("family_category", "is_primary", "category_is_primary", "Primary category"),
                ]
            if kind == "GOODS" and configuration.options.manufacturer_mode != "DISABLED":
                mappings += [
                    ("family_manufacturer", "manufacturer_id", "manufacturer_id", "Manufacturer"),
                    ("family_manufacturer", "site_id", "manufacturer_site_id", "Manufacturer site"),
                ]
            if configuration.options.barcode_mode != "DISABLED":
                mappings += [
                    ("item_barcode", "value", "barcode_value", "Barcode value"),
                    ("item_barcode", "symbology", "barcode_symbology", "Barcode format"),
                ]
            if profile.default_tax_system == "gst_in":
                mappings += [
                    (
                        "catalog_tax_binding",
                        "classification_id",
                        "classification_id",
                        "HSN" if kind == "GOODS" else "SAC",
                    ),
                    ("catalog_tax_binding", "rule_id", "rule_id", "GST treatment / rate"),
                ]
            if configuration.pricing.sale_price_mode != "DISABLED":
                if sale_levels:
                    mappings.extend(
                        (
                            "item_price_draft",
                            "amount",
                            "sale_prices." + str(level.price_level_id),
                            level.name,
                        )
                        for level in sale_levels
                    )
                else:
                    mappings.append(("item_price_draft", "amount", "sale_price", "Selling price"))
            if configuration.pricing.purchase_reference_mode != "DISABLED" and current.allows_scope(
                "purchase_price.read", target=ScopePath(company_id=company_id)
            ):
                mappings.append(("item_price_draft", "amount", "purchase_price", "Purchase price"))
            if kind == "GOODS" and configuration.pricing.mrp_mode != "DISABLED":
                mappings.append(("item_mrp", "amount", "mrp", "MRP"))
            native_fields: dict[str, list[FieldMetadata]] = {}
            for entity, native_key, key, label in mappings:
                if entity not in native_fields:
                    native_fields[entity] = (
                        await field_set(
                            company_id,
                            "catalog." + entity,
                            metadata_request,
                            "create",
                            None,
                            current,
                            db,
                        )
                    ).fields
                selected = next(
                    (field for field in native_fields[entity] if field.key == native_key), None
                )
                if selected:
                    if key == "purchase_price":
                        selected = selected.model_copy(
                            update={
                                "writable": selected.writable
                                and current.allows_scope(
                                    "purchase_price.manage", target=ScopePath(company_id=company_id)
                                )
                            }
                        )
                    selected = selected.model_copy(update={"key": key, "label": label})
                    if key.startswith("sale_prices."):
                        selected.required = next(
                            level.required
                            for level in sale_levels
                            if key == "sale_prices." + str(level.price_level_id)
                        )
                    if key == "barcode_symbology":
                        selected.control = ConfigurationControl(
                            kind="select",
                            label=label,
                            choices=[
                                ConfigurationChoice(value=value, label=title)
                                for value, title in (
                                    ("CODE128", "Code 128"),
                                    ("GTIN", "GTIN"),
                                    ("QR", "QR"),
                                )
                            ],
                        )
                    fields.append(selected)
            result = SimpleCreationOptions(
                company_id=company_id,
                kind=kind,
                today=today,
                opening_date=facts.finance.books_begin_date,
                currency=facts.base_currency,
                field_set=basic,
                configuration=configuration,
                default_group_id=group,
                inventory_enabled="inventory" in facts.features,
                gst_enabled=profile.default_tax_system == "gst_in",
                fields=fields,
                sale_price_levels=sale_levels,
                required_category_schemes=category_schemes,
                batch=SimpleBatchOptions.model_validate(batch),
                serial=serial,
            )
    if (
        result.inventory_enabled
        and kind == "GOODS"
        and current.allows_scope("accounting.stock.read", target=ScopePath(company_id=company_id))
    ):
        metadata = await owners(request).call(
            "accounting", "GET", f"/v1/companies/{company_id}/stock/openings/capture-fields"
        )
        quantity = next((field for field in metadata["fields"] if field["key"] == "quantity"), None)
        if quantity:
            result.fields.append(
                FieldMetadata(
                    key="opening_quantity",
                    source="native",
                    label="Opening quantity",
                    required=False,
                    visible=quantity["visible"] and quantity["readable"],
                    order=100,
                    writable=quantity["writable"],
                    conditional_access=False,
                )
            )
    if result.serial.enabled and current.allows_scope(
        "accounting.serial.read", target=ScopePath(company_id=company_id)
    ):
        metadata = await owners(request).call(
            "accounting",
            "GET",
            f"/v1/companies/{company_id}/stock-tracking/serials/field-set?action=prepare",
        )
        selected = next((row for row in metadata["fields"] if row["key"] == "identifiers"), None)
        if selected:
            result.fields.append(
                FieldMetadata(
                    key="serial_identifiers",
                    source="native",
                    label="Serial identifiers",
                    required=False,
                    visible=selected["visible"] and selected["readable"],
                    order=110,
                    writable=selected["writable"],
                    conditional_access=False,
                )
            )
    if result.batch.available and current.allows_scope(
        "accounting.batch.read", target=ScopePath(company_id=company_id)
    ):
        metadata = await owners(request).call(
            "accounting",
            "GET",
            f"/v1/companies/{company_id}/stock-tracking/batches/field-set?action=prepare",
        )
        for key, label in (
            ("code", "Batch"),
            ("manufactured_on", "Manufacture date"),
            ("expires_on", "Expiry date"),
            ("mrp_amount", "Batch MRP"),
        ):
            selected = next((value for value in metadata["fields"] if value["key"] == key), None)
            if selected:
                result.fields.append(
                    FieldMetadata(
                        key="batch_" + key,
                        source="native",
                        label=label,
                        required=key == "code",
                        visible=selected["visible"] and selected["readable"],
                        writable=selected["writable"],
                        conditional_access=False,
                        order=110,
                    )
                )
    return result


@router.post(
    "",
    response_model=SimpleCreationStatus,
    status_code=201,
    operation_id="start_simple_product_creation",
)
async def start(
    company_id: uuid.UUID,
    body: SimpleCreationInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> SimpleCreationStatus:
    no_query(request)
    limit(request, current, company_id)
    return await tasks.start(
        request.app.state.session_factory,
        current,
        context(request, company_id, current),
        body,
        key,
        owners(request),
    )


@router.get(
    "/by-key/{command_key}",
    response_model=SimpleCreationStatus,
    operation_id="find_simple_product_creation",
)
async def by_key(
    company_id: uuid.UUID, command_key: uuid.UUID, request: Request, current: Actor = Depends(actor)
) -> SimpleCreationStatus:
    from billing_platform.errors import NotFoundError

    from catalog.models.simple_product_creation import SimpleProductCreation

    no_query(request)
    current.require_scope("item.read", target=ScopePath(company_id=company_id))
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            identity = await db.scalar(
                select(SimpleProductCreation.id).where(
                    SimpleProductCreation.company_id == company_id,
                    SimpleProductCreation.command_key == str(command_key),
                    SimpleProductCreation.created_by == current.user_id,
                )
            )
            if identity is None:
                raise NotFoundError("No product creation was saved with this key")
    return await tasks.read(request.app.state.session_factory, current, company_id, identity)


@router.get(
    "/{creation_id}",
    response_model=SimpleCreationStatus,
    operation_id="get_simple_product_creation",
)
async def read(
    company_id: uuid.UUID, creation_id: uuid.UUID, request: Request, current: Actor = Depends(actor)
) -> SimpleCreationStatus:
    no_query(request)
    return await tasks.read(request.app.state.session_factory, current, company_id, creation_id)


@router.post(
    "/{creation_id}/advance",
    response_model=SimpleCreationStatus,
    operation_id="advance_simple_product_creation",
)
async def advance(
    company_id: uuid.UUID, creation_id: uuid.UUID, request: Request, current: Actor = Depends(actor)
) -> SimpleCreationStatus:
    no_query(request)
    limit(request, current, company_id)
    return await tasks.advance(
        request.app.state.session_factory,
        current,
        context(request, company_id, current),
        creation_id,
        owners(request),
    )


@router.patch(
    "/{creation_id}",
    response_model=SimpleCreationStatus,
    operation_id="revise_simple_product_creation",
)
async def revise(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    body: SimpleCreationRevision,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> SimpleCreationStatus:
    no_query(request)
    limit(request, current, company_id)
    return await tasks.revise(
        request.app.state.session_factory,
        current,
        context(request, company_id, current),
        creation_id,
        body.product,
        body.expected_version,
        key,
        owners(request),
    )
