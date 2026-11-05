"""Promotion-limit identity routes use the shared company-scoped master pipeline."""

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
from catalog.schemas.definition_revisions import DefinitionAuthoringContext
from catalog.schemas.promotion_limits import (
    LimitCreate,
    LimitDetail,
    LimitListItem,
    LimitQuery,
    LimitUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.field_context import load_field_context
from catalog.tasks.profiles import PROMOTION_LIMIT

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/promotion-limits/authoring-context",
    response_model=DefinitionAuthoringContext,
    operation_id="get_catalog_promotion_limit_authoring_context",
    dependencies=[Depends(no_query)],
)
async def authoring_context(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> DefinitionAuthoringContext:
    context = await load_field_context(
        db, current, company_id, "catalog.promotion_limit_definition"
    )
    return DefinitionAuthoringContext(
        company_id=company_id, enabled={"sales_promotions"} <= context.features
    )


@router.get(
    "/promotion-limits",
    response_model=Page[LimitListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_promotion_limit",
    dependencies=[Depends(unique_query)],
)
async def list_promotion_limit(
    company_id: uuid.UUID,
    query: Annotated[LimitQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        PROMOTION_LIMIT,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/promotion-limits/{object_id}",
    response_model=LimitDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_promotion_limit",
)
async def get_promotion_limit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, PROMOTION_LIMIT)


@router.post(
    "/promotion-limits",
    response_model=LimitDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_promotion_limit",
    status_code=201,
)
async def create_promotion_limit(
    company_id: uuid.UUID,
    body: LimitCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PROMOTION_LIMIT, body, idempotency_key, "create"
    )


@router.patch(
    "/promotion-limits/{object_id}",
    response_model=LimitDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_promotion_limit",
)
async def update_promotion_limit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: LimitUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        PROMOTION_LIMIT,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/promotion-limits/{object_id}/activate",
    response_model=LimitDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_promotion_limit",
)
async def activate_promotion_limit(
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
        PROMOTION_LIMIT,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/promotion-limits/{object_id}/deactivate",
    response_model=LimitDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_promotion_limit",
)
async def deactivate_promotion_limit(
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
        PROMOTION_LIMIT,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
