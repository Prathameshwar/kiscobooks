"""Bounded row progress for Simple imports; native creation owns every business effect."""

import uuid
from typing import Annotated

from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request

from catalog.api.auth import actor
from catalog.api.master_imports import build
from catalog.api.simple_product_creation import limit, no_store
from catalog.api.units import no_query, unique_query
from catalog.schemas.simple_product_import import SimpleImportProgress, SimpleImportRowResult
from catalog.tasks import simple_import_execution as tasks

router = APIRouter(
    prefix="/v1/companies/{company_id}/simple-product-imports",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
    dependencies=[Depends(unique_query), Depends(no_store)],
)


@router.get(
    "/{job_id}/progress",
    response_model=SimpleImportProgress,
    operation_id="get_simple_product_import_progress",
)
async def progress(
    company_id: uuid.UUID, job_id: uuid.UUID, request: Request, current: Actor = Depends(actor)
) -> SimpleImportProgress:
    no_query(request)
    return await tasks.read(await build(request, current, company_id), job_id)


@router.get(
    "/{job_id}/rows",
    response_model=Page[SimpleImportRowResult],
    operation_id="list_simple_product_import_results",
)
async def rows(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    cursor: Annotated[str | None, Query(max_length=3000)] = None,
    current: Actor = Depends(actor),
) -> Page[SimpleImportRowResult]:
    if set(request.query_params) - {"limit", "cursor"}:
        raise ValidationFailedError("Unknown import result query")
    return Page[SimpleImportRowResult].model_validate(
        await tasks.rows(await build(request, current, company_id), job_id, limit, cursor)
    )


@router.post(
    "/{job_id}/advance",
    response_model=SimpleImportProgress,
    operation_id="advance_simple_product_import",
)
async def advance(
    company_id: uuid.UUID, job_id: uuid.UUID, request: Request, current: Actor = Depends(actor)
) -> SimpleImportProgress:
    no_query(request)
    limit(request, current, company_id)
    return await tasks.advance(await build(request, current, company_id), job_id)
