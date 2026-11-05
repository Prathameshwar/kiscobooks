"""Company-scoped identifier definitions using the native master command pipeline."""

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
from catalog.api.units import Idempotency, no_query, signing_secret, unique_query, write
from catalog.schemas.identifier_masters import (
    IdentifierNamespaceCreate,
    IdentifierNamespaceDetail,
    IdentifierNamespaceListItem,
    IdentifierNamespaceQuery,
    IdentifierNamespaceUpdate,
    IdentifierTypeCreate,
    IdentifierTypeDetail,
    IdentifierTypeListItem,
    IdentifierTypeQuery,
    IdentifierTypeUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.unit_masters import (
    IDENTIFIER_NAMESPACE,
    IDENTIFIER_TYPE,
    list_masters,
    read_master,
)

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/identifier-types",
    response_model=Page[IdentifierTypeListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_identifier_type",
    dependencies=[Depends(unique_query)],
)
async def list_identifier_type(
    company_id: uuid.UUID,
    query: Annotated[IdentifierTypeQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_masters(
        db, current, company_id, IDENTIFIER_TYPE, query, signing_secret(request)
    )


@router.get(
    "/identifier-types/{object_id}",
    response_model=IdentifierTypeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_identifier_type",
)
async def get_identifier_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read_master(db, current, company_id, object_id, IDENTIFIER_TYPE)


@router.post(
    "/identifier-types",
    response_model=IdentifierTypeDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_identifier_type",
)
async def create_identifier_type(
    company_id: uuid.UUID,
    body: IdentifierTypeCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, IDENTIFIER_TYPE, body, idempotency_key, "create"
    )


@router.patch(
    "/identifier-types/{object_id}",
    response_model=IdentifierTypeDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_identifier_type",
)
async def update_identifier_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: IdentifierTypeUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, IDENTIFIER_TYPE, body, idempotency_key, "update", object_id
    )


@router.post(
    "/identifier-types/{object_id}/activate",
    response_model=IdentifierTypeDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_identifier_type",
)
async def activate_identifier_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, IDENTIFIER_TYPE, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/identifier-types/{object_id}/deactivate",
    response_model=IdentifierTypeDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_identifier_type",
)
async def deactivate_identifier_type(
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
        IDENTIFIER_TYPE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/identifier-namespaces",
    response_model=Page[IdentifierNamespaceListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_identifier_namespace",
    dependencies=[Depends(unique_query)],
)
async def list_identifier_namespace(
    company_id: uuid.UUID,
    query: Annotated[IdentifierNamespaceQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_masters(
        db, current, company_id, IDENTIFIER_NAMESPACE, query, signing_secret(request)
    )


@router.get(
    "/identifier-namespaces/{object_id}",
    response_model=IdentifierNamespaceDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_identifier_namespace",
)
async def get_identifier_namespace(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read_master(db, current, company_id, object_id, IDENTIFIER_NAMESPACE)


@router.post(
    "/identifier-namespaces",
    response_model=IdentifierNamespaceDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_identifier_namespace",
)
async def create_identifier_namespace(
    company_id: uuid.UUID,
    body: IdentifierNamespaceCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, IDENTIFIER_NAMESPACE, body, idempotency_key, "create"
    )


@router.patch(
    "/identifier-namespaces/{object_id}",
    response_model=IdentifierNamespaceDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_identifier_namespace",
)
async def update_identifier_namespace(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: IdentifierNamespaceUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        IDENTIFIER_NAMESPACE,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/identifier-namespaces/{object_id}/activate",
    response_model=IdentifierNamespaceDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_identifier_namespace",
)
async def activate_identifier_namespace(
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
        IDENTIFIER_NAMESPACE,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/identifier-namespaces/{object_id}/deactivate",
    response_model=IdentifierNamespaceDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_identifier_namespace",
)
async def deactivate_identifier_namespace(
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
        IDENTIFIER_NAMESPACE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
