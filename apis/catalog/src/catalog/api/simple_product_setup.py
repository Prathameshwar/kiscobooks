"""Single-product adapters reuse native owner checks and atomic commands."""

import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.simple_products import secret
from catalog.api.units import Idempotency, no_query
from catalog.models.products import Item
from catalog.schemas.product_authoring import (
    CategoryAssignmentInput,
    FamilyAttributesInput,
    GroupAssignmentInput,
    ManufacturerAssignmentInput,
)
from catalog.schemas.simple_product_setup import (
    ProductAttributesInput,
    ProductCategoriesInput,
    ProductGroupInput,
    ProductManufacturerInput,
    ProductSetupGuard,
    SimpleProductAttributeForm,
    SimpleProductCategoryPreview,
)
from catalog.schemas.simple_products import SimpleProductDetail
from catalog.schemas.units import ExpectedVersion
from catalog.tasks import product_attributes, product_classification
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.product_commands import ProductWork, execute
from catalog.tasks.simple_products import ProductGuard, decode_revision, read

router = APIRouter(
    prefix="/v1/companies/{company_id}/products",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post(
    "/{item_id}/category-preview",
    response_model=SimpleProductCategoryPreview,
    operation_id="preview_catalog_simple_product_categories",
)
async def category_preview(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ProductCategoriesInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SimpleProductCategoryPreview:
    from catalog.models.products import ProductFamily
    from catalog.tasks.category_schedule import prepare

    no_query(request)
    access = ConfigurationAccess(db, current, company_id)
    item = await access.reference(Item, item_id)
    family = await access.reference(ProductFamily, item.family_id)
    # Preview does not mutate; commit rechecks these versions under the company lock.
    product = await read(db, current, company_id, item_id, secret(request))
    reviewed = decode_revision(current, company_id, item_id, secret(request), body.revision)
    from billing_platform.errors import ConflictError

    from catalog.tasks.simple_products import assert_simple, revision_values

    await assert_simple(db, company_id, item, family)
    if (
        reviewed != revision_values(item, family)
        or body.authoring_version != product.authoring_version
    ):
        raise ConflictError("Product changed; reload before previewing.")
    native = CategoryAssignmentInput.model_validate(
        {
            **body.model_dump(exclude={"revision", "authoring_version"}),
            "expected_version": family.row_version,
        }
    )
    result = await prepare(
        ProductWork(db, current, company_id, family, None, access), native, secret(request)
    )
    return SimpleProductCategoryPreview(
        id=item_id,
        revision=body.revision,
        authoring_version=product.authoring_version,
        preview_token=result.preview_token,
        membership_count=result.membership_count,
        closing_count=result.closing_count,
    )


@router.get(
    "/{item_id}/attribute-form",
    response_model=SimpleProductAttributeForm,
    operation_id="get_catalog_simple_product_attribute_form",
)
async def attribute_form(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SimpleProductAttributeForm:
    from catalog.tasks.attribute_forms import form

    no_query(request)
    native = await form(db, current, company_id, item_id)
    product = await read(db, current, company_id, item_id, secret(request))
    return SimpleProductAttributeForm(
        id=item_id,
        name=native.item_name,
        status=native.item_status,
        revision=product.revision,
        authoring_version=product.authoring_version,
        base_unit_id=native.base_unit_id,
        base_unit_label=native.base_unit_label,
        can_configure=native.can_configure,
        fields=native.fields,
    )


async def setup(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    item_id: uuid.UUID,
    body: ProductSetupGuard,
    key: str,
    schema: type[ExpectedVersion],
    action: str,
    handler: Any,
) -> JSONResponse:
    no_query(request)
    signing_secret = secret(request)
    reviewed = decode_revision(current, company, item_id, signing_secret, body.revision)
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            access = ConfigurationAccess(db, current, company)
            item = await access.reference(Item, item_id)
            family_id = item.family_id
    values = body.model_dump(exclude={"revision", "authoring_version"})
    if isinstance(body, ProductAttributesInput):
        values["default_item_attributes"] = values.pop("values")
        values["expected_default_item_version"] = reviewed["item_version"]
    native = schema.model_validate({"expected_version": reviewed["family_version"], **values})
    result = await execute(
        request.app.state.session_factory,
        current,
        company,
        family_id,
        native,
        key,
        action,
        handler,
        product_guard=ProductGuard(item_id, body.revision, body.authoring_version, signing_secret),
    )
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            product = await read(db, current, company, item_id, signing_secret)
    return JSONResponse(
        status_code=result.status,
        content=product.model_dump(mode="json", exclude_unset=True),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/{item_id}/groups",
    response_model=SimpleProductDetail,
    operation_id="assign_group_catalog_simple_product",
)
async def group(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ProductGroupInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await setup(
        request,
        current,
        company_id,
        item_id,
        body,
        idempotency_key,
        GroupAssignmentInput,
        "assign_group",
        product_classification.assign_group,
    )


@router.post(
    "/{item_id}/manufacturers",
    response_model=SimpleProductDetail,
    operation_id="assign_manufacturer_catalog_simple_product",
)
async def manufacturer(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ProductManufacturerInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await setup(
        request,
        current,
        company_id,
        item_id,
        body,
        idempotency_key,
        ManufacturerAssignmentInput,
        "assign_manufacturer",
        product_classification.assign_manufacturer,
    )


@router.put(
    "/{item_id}/categories",
    response_model=SimpleProductDetail,
    operation_id="assign_categories_catalog_simple_product",
)
async def categories(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ProductCategoriesInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    async def commit(work: ProductWork, incoming: CategoryAssignmentInput) -> None:
        await product_classification.assign_categories(work, incoming, secret(request))

    return await setup(
        request,
        current,
        company_id,
        item_id,
        body,
        idempotency_key,
        CategoryAssignmentInput,
        "assign_categories",
        commit,
    )


@router.put(
    "/{item_id}/attributes",
    response_model=SimpleProductDetail,
    operation_id="configure_attributes_catalog_simple_product",
)
async def attributes(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ProductAttributesInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await setup(
        request,
        current,
        company_id,
        item_id,
        body,
        idempotency_key,
        FamilyAttributesInput,
        "configure_attributes",
        product_attributes.configure_family,
    )
