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
from catalog.schemas.manufacturing_operations import (
    OperationCreate,
    OperationDetail,
    OperationListItem,
    OperationQuery,
    OperationServiceOption,
    OperationServiceQuery,
    OperationUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.configuration_options import options
from catalog.tasks.profiles import MANUFACTURING_OPERATION

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/manufacturing-operations/service-options",
    response_model=Page[OperationServiceOption],
    operation_id="list_manufacturing_operation_services",
    dependencies=[Depends(unique_query)],
)
async def service_options(
    company_id: uuid.UUID,
    query: Annotated[OperationServiceQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[OperationServiceOption]:
    result = await options(
        db,
        current,
        company_id,
        "items",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        owner_permission="manufacturing_operation.read",
        owner_entity="catalog.manufacturing_operation",
        active_items_only=True,
    )
    return Page(
        items=[
            OperationServiceOption(id=uuid.UUID(row.value), name=row.label, sku=row.code)
            for row in result.items
        ],
        page=result.page,
    )


@router.get(
    "/manufacturing-operations",
    response_model=Page[OperationListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_manufacturing_operation",
    dependencies=[Depends(unique_query)],
)
async def list_manufacturing_operation(
    company_id: uuid.UUID,
    query: Annotated[OperationQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        MANUFACTURING_OPERATION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/manufacturing-operations/{object_id}",
    response_model=OperationDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_manufacturing_operation",
)
async def get_manufacturing_operation(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, MANUFACTURING_OPERATION)


@router.post(
    "/manufacturing-operations",
    response_model=OperationDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_manufacturing_operation",
    status_code=201,
)
async def create_manufacturing_operation(
    company_id: uuid.UUID,
    body: OperationCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, MANUFACTURING_OPERATION, body, idempotency_key, "create"
    )


@router.patch(
    "/manufacturing-operations/{object_id}",
    response_model=OperationDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_manufacturing_operation",
)
async def update_manufacturing_operation(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OperationUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        MANUFACTURING_OPERATION,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/manufacturing-operations/{object_id}/activate",
    response_model=OperationDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_manufacturing_operation",
)
async def activate_manufacturing_operation(
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
        MANUFACTURING_OPERATION,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/manufacturing-operations/{object_id}/deactivate",
    response_model=OperationDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_manufacturing_operation",
)
async def deactivate_manufacturing_operation(
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
        MANUFACTURING_OPERATION,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
