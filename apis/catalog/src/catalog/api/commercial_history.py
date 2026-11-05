"""Commercial history routes; history commands stay transactional in tasks."""

import uuid
from typing import Annotated, Literal

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.schemas.commercial import (
    BrandManufacturerClose,
    BrandManufacturerCreate,
    BrandManufacturerDetail,
    BrandManufacturerListItem,
    BrandManufacturerQuery,
    TypeRevisionDetail,
    TypeRevisionInput,
    TypeRevisionListItem,
    TypeRevisionQuery,
    TypeRevisionUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.commercial_history import PRODUCTION, REVISION, History, command, list_rows, read

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    spec: History,
    body: BaseModel,
    key: str,
    action: Literal["create", "update", "close", "publish", "retire"],
    object_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company,
        spec,
        body=body,
        key=key,
        action=action,
        object_id=object_id,
        parent_id=parent_id,
    )
    return command_response(request, result, created=action == "create")


@router.get(
    "/brand-manufacturers",
    response_model=Page[BrandManufacturerListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_production",
    dependencies=[Depends(unique_query)],
)
async def list_production(
    company_id: uuid.UUID,
    query: Annotated[BrandManufacturerQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        PRODUCTION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/brand-manufacturers/{object_id}",
    response_model=BrandManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_production",
)
async def get_production(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, PRODUCTION)


@router.post(
    "/brand-manufacturers",
    response_model=BrandManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_production",
    status_code=201,
)
async def create_production(
    company_id: uuid.UUID,
    body: BrandManufacturerCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, PRODUCTION, body, idempotency_key, "create")


@router.post(
    "/brand-manufacturers/{object_id}/close",
    response_model=BrandManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="close_catalog_production",
)
async def close_production(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BrandManufacturerClose,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PRODUCTION, body, idempotency_key, "close", object_id
    )


@router.get(
    "/product-types/{product_type_id}/revisions",
    response_model=Page[TypeRevisionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_type_revision",
    dependencies=[Depends(unique_query)],
)
async def list_type_revision(
    company_id: uuid.UUID,
    product_type_id: uuid.UUID,
    query: Annotated[TypeRevisionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        REVISION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        product_type_id,
    )


@router.get(
    "/product-types/{product_type_id}/revisions/{object_id}",
    response_model=TypeRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_type_revision",
)
async def get_type_revision(
    company_id: uuid.UUID,
    product_type_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, REVISION, product_type_id)


@router.post(
    "/product-types/{product_type_id}/revisions",
    response_model=TypeRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_type_revision",
    status_code=201,
)
async def create_type_revision(
    company_id: uuid.UUID,
    product_type_id: uuid.UUID,
    body: TypeRevisionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        REVISION,
        body,
        idempotency_key,
        "create",
        None,
        product_type_id,
    )


@router.patch(
    "/product-types/{product_type_id}/revisions/{object_id}",
    response_model=TypeRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_type_revision",
)
async def update_type_revision(
    company_id: uuid.UUID,
    product_type_id: uuid.UUID,
    object_id: uuid.UUID,
    body: TypeRevisionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        REVISION,
        body,
        idempotency_key,
        "update",
        object_id,
        product_type_id,
    )


@router.post(
    "/product-types/{product_type_id}/revisions/{object_id}/publish",
    response_model=TypeRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="publish_catalog_type_revision",
)
async def publish_type_revision(
    company_id: uuid.UUID,
    product_type_id: uuid.UUID,
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
        REVISION,
        body,
        idempotency_key,
        "publish",
        object_id,
        product_type_id,
    )
