"""Promotion-limit definitions reuse the common revision command and history pipeline."""

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
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.schemas.promotion_limits import (
    LimitRevisionDetail,
    LimitRevisionInput,
    LimitRevisionListItem,
    LimitRevisionQuery,
    LimitRevisionUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.definition_revisions import command, list_rows, read
from catalog.tasks.promotion_limits import LIMIT_REVISION

router = APIRouter(
    prefix="/v1/companies/{company_id}/promotion-limits/{definition_id}/revisions",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "",
    response_model=Page[LimitRevisionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_promotion_limit_revisions",
    dependencies=[Depends(unique_query)],
)
async def revisions(
    company_id: uuid.UUID,
    definition_id: uuid.UUID,
    query: Annotated[LimitRevisionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        definition_id,
        LIMIT_REVISION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/{object_id}",
    response_model=LimitRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_promotion_limit_revision",
)
async def revision(
    company_id: uuid.UUID,
    definition_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, definition_id, object_id, LIMIT_REVISION)


@router.post(
    "",
    response_model=LimitRevisionDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_promotion_limit_revision",
)
async def create_revision(
    company_id: uuid.UUID,
    definition_id: uuid.UUID,
    body: LimitRevisionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        definition_id,
        LIMIT_REVISION,
        body,
        idempotency_key,
        "create",
        None,
    )
    return command_response(request, result, created=True)


@router.patch(
    "/{object_id}",
    response_model=LimitRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_promotion_limit_revision",
)
async def update_revision(
    company_id: uuid.UUID,
    definition_id: uuid.UUID,
    object_id: uuid.UUID,
    body: LimitRevisionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        definition_id,
        LIMIT_REVISION,
        body,
        idempotency_key,
        "update",
        object_id,
    )
    return command_response(request, result, created=False)


@router.post(
    "/{object_id}/publish",
    response_model=LimitRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="publish_catalog_promotion_limit_revision",
)
async def publish_revision(
    company_id: uuid.UUID,
    definition_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        definition_id,
        LIMIT_REVISION,
        body,
        idempotency_key,
        "publish",
        object_id,
    )
    return command_response(request, result, created=False)
