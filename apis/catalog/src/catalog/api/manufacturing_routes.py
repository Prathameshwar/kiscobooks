"""Manufacturing operation identities; specifications live in immutable revisions."""

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
from catalog.schemas.manufacturing_routes import (
    OperationReferenceQuery,
    OperationRevisionOption,
    RouteCreate,
    RouteDetail,
    RouteListItem,
    RouteQuery,
    RouteUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.manufacturing_routes import operation_options, operation_reference
from catalog.tasks.profiles import MANUFACTURING_ROUTE

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/manufacturing-routes/operation-options",
    response_model=Page[OperationRevisionOption],
    operation_id="list_catalog_route_operation_options",
    dependencies=[Depends(unique_query)],
)
async def route_operation_options(
    company_id: uuid.UUID,
    query: Annotated[OperationReferenceQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[OperationRevisionOption]:
    return await operation_options(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/manufacturing-routes/operation-references/{reference_id}",
    response_model=OperationRevisionOption,
    operation_id="get_catalog_route_operation_reference",
    dependencies=[Depends(no_query)],
)
async def route_operation_reference(
    company_id: uuid.UUID,
    reference_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> OperationRevisionOption:
    return await operation_reference(db, current, company_id, reference_id)


@router.get(
    "/manufacturing-routes",
    response_model=Page[RouteListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_manufacturing_route",
    dependencies=[Depends(unique_query)],
)
async def list_manufacturing_route(
    company_id: uuid.UUID,
    query: Annotated[RouteQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        MANUFACTURING_ROUTE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/manufacturing-routes/{object_id}",
    response_model=RouteDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_manufacturing_route",
)
async def get_manufacturing_route(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, MANUFACTURING_ROUTE)


@router.post(
    "/manufacturing-routes",
    response_model=RouteDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_manufacturing_route",
    status_code=201,
)
async def create_manufacturing_route(
    company_id: uuid.UUID,
    body: RouteCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURING_ROUTE, body, idempotency_key, "create"
    )


@router.patch(
    "/manufacturing-routes/{object_id}",
    response_model=RouteDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_manufacturing_route",
)
async def update_manufacturing_route(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: RouteUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        MANUFACTURING_ROUTE,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/manufacturing-routes/{object_id}/activate",
    response_model=RouteDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_manufacturing_route",
)
async def activate_manufacturing_route(
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
        MANUFACTURING_ROUTE,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/manufacturing-routes/{object_id}/deactivate",
    response_model=RouteDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_manufacturing_route",
)
async def deactivate_manufacturing_route(
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
        MANUFACTURING_ROUTE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
