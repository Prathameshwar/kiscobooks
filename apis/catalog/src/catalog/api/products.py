"""Thin product/SKU draft routes with standard auth and list contracts."""

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
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.schemas.products import (
    FamilyCreate,
    FamilyDetail,
    FamilyListItem,
    FamilyPatch,
    FamilyQuery,
    ItemDetail,
    ItemListItem,
    ItemPatch,
    ItemQuery,
    ProductCreated,
)
from catalog.tasks.products import command, list_rows, read

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company_id: uuid.UUID,
    body: FamilyCreate | FamilyPatch | ItemPatch,
    key: str,
    *,
    object_id: uuid.UUID | None = None,
    item: bool = False,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        body,
        key,
        object_id=object_id,
        item=item,
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json", exclude_unset=True),
        headers={
            "Idempotency-Replayed": str(result.replayed).lower(),
            "Cache-Control": "no-store",
            **(
                {
                    "Location": request.url.path
                    + "/"
                    + str(result.value.model_dump()["family"]["id"])
                }
                if isinstance(body, FamilyCreate)
                else {}
            ),
        },
    )


@router.post(
    "/product-families",
    response_model=ProductCreated,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_product_family",
)
async def create_family(
    company_id: uuid.UUID,
    body: FamilyCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key)


@router.get(
    "/product-families",
    response_model=Page[FamilyListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_product_family",
    dependencies=[Depends(unique_query)],
)
async def list_product_family(
    company_id: uuid.UUID,
    query: Annotated[FamilyQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        item=False,
    )


@router.get(
    "/product-families/{object_id}",
    response_model=FamilyDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_product_family",
)
async def get_product_family(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, item=False)


@router.patch(
    "/product-families/{object_id}",
    response_model=FamilyDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_product_family",
)
async def update_product_family(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: FamilyPatch,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, idempotency_key, object_id=object_id, item=False
    )


@router.get(
    "/items",
    response_model=Page[ItemListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_item",
    dependencies=[Depends(unique_query)],
)
async def list_item(
    company_id: uuid.UUID,
    query: Annotated[ItemQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        item=True,
    )


@router.get(
    "/items/{object_id}",
    response_model=ItemDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item",
)
async def get_item(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, item=True)


@router.patch(
    "/items/{object_id}",
    response_model=ItemDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_item",
)
async def update_item(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ItemPatch,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, idempotency_key, object_id=object_id, item=True
    )
