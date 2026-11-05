"""Additive single-product facade over native Catalog commands."""

import uuid
from typing import Annotated, Any, Literal

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.schemas.simple_products import (
    SimpleProductCreate,
    SimpleProductDetail,
    SimpleProductFieldSet,
    SimpleProductListItem,
    SimpleProductPatch,
    SimpleProductQuery,
)
from catalog.tasks import simple_products
from catalog.tasks.products import command

router = APIRouter(
    prefix="/v1/companies/{company_id}/products",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


def secret(request: Request) -> bytes:
    value: str = request.app.state.settings.actor_signing_secret.get_secret_value()
    return value.encode()


@router.get(
    "/field-set",
    response_model=SimpleProductFieldSet,
    operation_id="get_catalog_simple_product_field_set",
)
async def product_field_set(
    company_id: uuid.UUID,
    request: Request,
    operation: Literal["create", "update"] = "create",
    object_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SimpleProductFieldSet:
    from billing_platform.db.access import company_object
    from billing_platform.errors import ValidationFailedError

    from catalog.api.field_metadata import field_set
    from catalog.models.products import Item
    from catalog.tasks.configuration_access import ConfigurationAccess
    from catalog.tasks.product_mode import version

    if object_id is not None and operation != "update":
        raise ValidationFailedError("object metadata requires an update operation")
    family_id = None
    if object_id is not None:
        access = ConfigurationAccess(db, current, company_id)
        item = await company_object(db, Item, object_id, company_id=company_id)
        await access.require(item, {"family_id"})
        family_id = item.family_id
    item_fields = await field_set(
        company_id, "catalog.item", request, operation, object_id, current, db
    )
    shared = await field_set(
        company_id, "catalog.product_family", request, operation, family_id, current, db
    )
    fields = []
    bindings = {}
    shared_name = next(
        (field for field in shared.fields if field.key == "name" and field.source == "native"), None
    )
    if shared_name is not None:
        bindings["catalog.product_family.name"] = "name"
    for field in item_fields.fields:
        if field.source == "custom":
            fields.append(field.model_copy(update={"key": "custom_fields." + field.key}))
            bindings["catalog.item.custom_field:" + field.key] = "custom_fields." + field.key
        elif field.key in {
            "sku",
            "name",
            "status",
            "base_unit_id",
            "sellable",
            "purchasable",
            "min_sale_quantity",
        }:
            updates: dict[str, Any] = {"key": "code" if field.key == "sku" else field.key}
            if field.key == "sku" and field.label.lower() == "sku":
                updates["label"] = "Product code"
            if field.key == "name":
                updates.update(
                    label="Product name" if field.label.lower() == "name" else field.label,
                    writable=field.writable and bool(shared_name and shared_name.writable),
                )
            fields.append(field.model_copy(update=updates))
            bindings["catalog.item." + field.key] = updates["key"]
    for field in shared.fields:
        if field.source == "custom":
            fields.append(field.model_copy(update={"key": "shared_custom_fields." + field.key}))
            bindings["catalog.product_family.custom_field:" + field.key] = (
                "shared_custom_fields." + field.key
            )
        elif field.key in {
            "kind",
            "product_type_revision_id",
            "brand_id",
            "series_id",
            "model_code",
            "description",
        }:
            fields.append(field)
            bindings["catalog.product_family." + field.key] = field.key
    if operation == "update":
        fields = [
            field.model_copy(update={"writable": False})
            if field.source == "native" and field.key not in SimpleProductPatch.model_fields
            else field
            for field in fields
        ]
    return SimpleProductFieldSet(
        company_id=company_id,
        source_version=item_fields.source_version,
        authoring_version=await version(db, company_id),
        fields=fields,
        native_bindings=bindings,
    )


@router.get(
    "",
    response_model=Page[SimpleProductListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_simple_products",
)
async def list_products(
    company_id: uuid.UUID,
    query: Annotated[SimpleProductQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[SimpleProductListItem]:
    return await simple_products.list_rows(db, current, company_id, query, secret(request))


@router.get(
    "/{item_id}",
    response_model=SimpleProductDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_simple_product",
)
async def read_product(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SimpleProductDetail:
    no_query(request)
    return await simple_products.read(db, current, company_id, item_id, secret(request))


async def write(
    company: uuid.UUID,
    body: SimpleProductCreate | SimpleProductPatch,
    request: Request,
    current: Actor,
    key: str,
    item_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company,
        body,
        key,
        object_id=item_id,
        secret=secret(request),
    )
    content = result.value.model_dump(mode="json", exclude_unset=True)
    return JSONResponse(
        status_code=result.status,
        content=content,
        headers={
            "Idempotency-Replayed": str(result.replayed).lower(),
            "Cache-Control": "no-store",
            **({"Location": request.url.path + "/" + content["id"]} if item_id is None else {}),
        },
    )


@router.post(
    "",
    response_model=SimpleProductDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_simple_product",
)
async def create(
    company_id: uuid.UUID,
    body: SimpleProductCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(company_id, body, request, current, idempotency_key)


@router.patch(
    "/{item_id}",
    response_model=SimpleProductDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_simple_product",
)
async def update(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: SimpleProductPatch,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(company_id, body, request, current, idempotency_key, item_id)
