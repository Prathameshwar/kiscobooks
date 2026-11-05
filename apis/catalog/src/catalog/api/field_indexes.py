"""Company/field-scoped index preparation commands and lean job history."""

import uuid
from typing import Annotated

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.schemas.field_indexes import (
    IndexStateDetail,
    RebuildCancel,
    RebuildDetail,
    RebuildListItem,
    RebuildQuery,
    RebuildStart,
)
from catalog.tasks.index_rebuilds import command, list_jobs, read_job, state_detail

router = APIRouter(
    prefix="/v1/companies/{company_id}/entities/{entity_type}/field-indexes/{field_key}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get("", response_model=IndexStateDetail, operation_id="get_catalog_field_index_state")
async def state(
    company_id: uuid.UUID,
    entity_type: str,
    field_key: str,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> IndexStateDetail:
    no_query(request)
    return await state_detail(db, current, company_id, entity_type, field_key)


@router.post(
    "/rebuilds",
    response_model=RebuildDetail,
    status_code=201,
    operation_id="start_catalog_field_index_rebuild",
)
async def start(
    company_id: uuid.UUID,
    entity_type: str,
    field_key: str,
    body: RebuildStart,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        entity_type,
        field_key,
        body,
        key=idempotency_key,
        action="start",
    )
    return command_response(request, result, created=True)


@router.post(
    "/rebuilds/{job_id}/cancel",
    response_model=RebuildDetail,
    operation_id="cancel_catalog_field_index_rebuild",
)
async def cancel(
    company_id: uuid.UUID,
    entity_type: str,
    field_key: str,
    job_id: uuid.UUID,
    body: RebuildCancel,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        entity_type,
        field_key,
        body,
        key=idempotency_key,
        action="cancel",
        job_id=job_id,
    )
    return command_response(request, result, created=False)


@router.get(
    "/rebuilds",
    response_model=Page[RebuildListItem],
    operation_id="list_catalog_field_index_rebuilds",
    dependencies=[Depends(unique_query)],
)
async def history(
    company_id: uuid.UUID,
    entity_type: str,
    field_key: str,
    query: Annotated[RebuildQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[RebuildListItem]:
    return await list_jobs(
        db,
        current,
        company_id,
        entity_type,
        field_key,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/rebuilds/{job_id}",
    response_model=RebuildDetail,
    operation_id="get_catalog_field_index_rebuild",
)
async def get_job(
    company_id: uuid.UUID,
    entity_type: str,
    field_key: str,
    job_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> RebuildDetail:
    no_query(request)
    return await read_job(db, current, company_id, entity_type, field_key, job_id)
