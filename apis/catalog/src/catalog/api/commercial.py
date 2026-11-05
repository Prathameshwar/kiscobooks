"""Thin commercial master routes with the shared Catalog API conventions."""

import uuid
from typing import Annotated

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.classification import write
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.schemas.commercial import (
    BrandCreate,
    BrandDetail,
    BrandListItem,
    BrandQuery,
    BrandReparent,
    BrandSeriesCreate,
    BrandSeriesDetail,
    BrandSeriesListItem,
    BrandSeriesQuery,
    BrandSeriesUpdate,
    BrandUpdate,
    ManufacturerCreate,
    ManufacturerDetail,
    ManufacturerListItem,
    ManufacturerQuery,
    ManufacturerSiteCreate,
    ManufacturerSiteDetail,
    ManufacturerSiteListItem,
    ManufacturerSiteQuery,
    ManufacturerSiteUpdate,
    ManufacturerUpdate,
    ProductTypeCreate,
    ProductTypeDetail,
    ProductTypeListItem,
    ProductTypeQuery,
    ProductTypeUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.commercial import (
    BRAND,
    BRAND_SERIES,
    MANUFACTURER,
    MANUFACTURER_SITE,
    PRODUCT_TYPE,
)

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/brands",
    response_model=Page[BrandListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_brand",
    dependencies=[Depends(unique_query)],
)
async def list_brand(
    company_id: uuid.UUID,
    query: Annotated[BrandQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        BRAND,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/brands/{object_id}",
    response_model=BrandDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_brand",
)
async def get_brand(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, BRAND)


@router.post(
    "/brands",
    response_model=BrandDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_brand",
    status_code=201,
)
async def create_brand(
    company_id: uuid.UUID,
    body: BrandCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, BRAND, body, idempotency_key, "create")


@router.patch(
    "/brands/{object_id}",
    response_model=BrandDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_brand",
)
async def update_brand(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BrandUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND, body, idempotency_key, "update", object_id
    )


@router.post(
    "/brands/{object_id}/activate",
    response_model=BrandDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_brand",
)
async def activate_brand(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/brands/{object_id}/deactivate",
    response_model=BrandDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_brand",
)
async def deactivate_brand(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND, body, idempotency_key, "deactivate", object_id
    )


@router.post(
    "/brands/{object_id}/reparent",
    response_model=BrandDetail,
    response_model_exclude_unset=True,
    operation_id="move_catalog_brand",
)
async def move_brand(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BrandReparent,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND, body, idempotency_key, "move", object_id
    )


@router.get(
    "/manufacturers",
    response_model=Page[ManufacturerListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_manufacturer",
    dependencies=[Depends(unique_query)],
)
async def list_manufacturer(
    company_id: uuid.UUID,
    query: Annotated[ManufacturerQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        MANUFACTURER,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/manufacturers/{object_id}",
    response_model=ManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_manufacturer",
)
async def get_manufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, MANUFACTURER)


@router.post(
    "/manufacturers",
    response_model=ManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_manufacturer",
    status_code=201,
)
async def create_manufacturer(
    company_id: uuid.UUID,
    body: ManufacturerCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, MANUFACTURER, body, idempotency_key, "create")


@router.patch(
    "/manufacturers/{object_id}",
    response_model=ManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_manufacturer",
)
async def update_manufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ManufacturerUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURER, body, idempotency_key, "update", object_id
    )


@router.post(
    "/manufacturers/{object_id}/activate",
    response_model=ManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_manufacturer",
)
async def activate_manufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURER, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/manufacturers/{object_id}/deactivate",
    response_model=ManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_manufacturer",
)
async def deactivate_manufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURER, body, idempotency_key, "deactivate", object_id
    )


@router.get(
    "/brand-series",
    response_model=Page[BrandSeriesListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_brand_series",
    dependencies=[Depends(unique_query)],
)
async def list_brand_series(
    company_id: uuid.UUID,
    query: Annotated[BrandSeriesQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        BRAND_SERIES,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/brand-series/{object_id}",
    response_model=BrandSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_brand_series",
)
async def get_brand_series(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, BRAND_SERIES)


@router.post(
    "/brand-series",
    response_model=BrandSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_brand_series",
    status_code=201,
)
async def create_brand_series(
    company_id: uuid.UUID,
    body: BrandSeriesCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, BRAND_SERIES, body, idempotency_key, "create")


@router.patch(
    "/brand-series/{object_id}",
    response_model=BrandSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_brand_series",
)
async def update_brand_series(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BrandSeriesUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND_SERIES, body, idempotency_key, "update", object_id
    )


@router.post(
    "/brand-series/{object_id}/activate",
    response_model=BrandSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_brand_series",
)
async def activate_brand_series(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND_SERIES, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/brand-series/{object_id}/deactivate",
    response_model=BrandSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_brand_series",
)
async def deactivate_brand_series(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, BRAND_SERIES, body, idempotency_key, "deactivate", object_id
    )


@router.get(
    "/manufacturer-sites",
    response_model=Page[ManufacturerSiteListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_manufacturer_site",
    dependencies=[Depends(unique_query)],
)
async def list_manufacturer_site(
    company_id: uuid.UUID,
    query: Annotated[ManufacturerSiteQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        MANUFACTURER_SITE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/manufacturer-sites/{object_id}",
    response_model=ManufacturerSiteDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_manufacturer_site",
)
async def get_manufacturer_site(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, MANUFACTURER_SITE)


@router.post(
    "/manufacturer-sites",
    response_model=ManufacturerSiteDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_manufacturer_site",
    status_code=201,
)
async def create_manufacturer_site(
    company_id: uuid.UUID,
    body: ManufacturerSiteCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURER_SITE, body, idempotency_key, "create"
    )


@router.patch(
    "/manufacturer-sites/{object_id}",
    response_model=ManufacturerSiteDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_manufacturer_site",
)
async def update_manufacturer_site(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ManufacturerSiteUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURER_SITE, body, idempotency_key, "update", object_id
    )


@router.post(
    "/manufacturer-sites/{object_id}/activate",
    response_model=ManufacturerSiteDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_manufacturer_site",
)
async def activate_manufacturer_site(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        MANUFACTURER_SITE,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/manufacturer-sites/{object_id}/deactivate",
    response_model=ManufacturerSiteDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_manufacturer_site",
)
async def deactivate_manufacturer_site(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        MANUFACTURER_SITE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/product-types",
    response_model=Page[ProductTypeListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_product_type",
    dependencies=[Depends(unique_query)],
)
async def list_product_type(
    company_id: uuid.UUID,
    query: Annotated[ProductTypeQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        PRODUCT_TYPE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-types/{object_id}",
    response_model=ProductTypeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_product_type",
)
async def get_product_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, PRODUCT_TYPE)


@router.post(
    "/product-types",
    response_model=ProductTypeDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_product_type",
    status_code=201,
)
async def create_product_type(
    company_id: uuid.UUID,
    body: ProductTypeCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, PRODUCT_TYPE, body, idempotency_key, "create")


@router.patch(
    "/product-types/{object_id}",
    response_model=ProductTypeDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_product_type",
)
async def update_product_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ProductTypeUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PRODUCT_TYPE, body, idempotency_key, "update", object_id
    )


@router.post(
    "/product-types/{object_id}/activate",
    response_model=ProductTypeDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_product_type",
)
async def activate_product_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PRODUCT_TYPE, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/product-types/{object_id}/deactivate",
    response_model=ProductTypeDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_product_type",
)
async def deactivate_product_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PRODUCT_TYPE, body, idempotency_key, "deactivate", object_id
    )
