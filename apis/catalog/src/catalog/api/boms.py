"""BOM identity routes use the shared company-scoped master pipeline."""

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
from catalog.schemas.boms import (
    AuthoringContext,
    BomCreate,
    BomDetail,
    BomListItem,
    BomQuery,
    BomUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.field_context import load_field_context
from catalog.tasks.profiles import BOM

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/boms/authoring-context",
    response_model=AuthoringContext,
    operation_id="get_catalog_bom_authoring_context",
    dependencies=[Depends(no_query)],
)
async def authoring_context(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> AuthoringContext:
    context = await load_field_context(db, current, company_id, "catalog.bom")
    return AuthoringContext(
        company_id=company_id, enabled={"inventory", "bom_definitions"} <= context.features
    )


@router.get(
    "/boms",
    response_model=Page[BomListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom",
    dependencies=[Depends(unique_query)],
)
async def list_bom(
    company_id: uuid.UUID,
    query: Annotated[BomQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        BOM,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/boms/{object_id}",
    response_model=BomDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_bom",
)
async def get_bom(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, BOM)


@router.post(
    "/boms",
    response_model=BomDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_bom",
    status_code=201,
)
async def create_bom(
    company_id: uuid.UUID,
    body: BomCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, BOM, body, idempotency_key, "create")


@router.patch(
    "/boms/{object_id}",
    response_model=BomDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_bom",
)
async def update_bom(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BomUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        BOM,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/boms/{object_id}/activate",
    response_model=BomDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_bom",
)
async def activate_bom(
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
        BOM,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/boms/{object_id}/deactivate",
    response_model=BomDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_bom",
)
async def deactivate_bom(
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
        BOM,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
