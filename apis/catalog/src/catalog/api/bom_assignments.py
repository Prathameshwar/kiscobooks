"""Permission-protected, dated BOM applicability; selection never claims execution readiness."""

import uuid
from typing import Annotated, Literal

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.schemas.boms import (
    AssignmentDetail,
    AssignmentInput,
    AssignmentListItem,
    AssignmentQuery,
    AssignmentUpdate,
    SelectionDetail,
    SelectionQuery,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks import bom_assignments

router = APIRouter(
    prefix="/v1/companies/{company_id}/bom-assignments",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/resolve",
    response_model=SelectionDetail,
    operation_id="resolve_catalog_bom_definition",
    dependencies=[Depends(unique_query)],
)
async def resolve_definition(
    company_id: uuid.UUID,
    query: Annotated[SelectionQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SelectionDetail:
    return await bom_assignments.resolve(db, current, company_id, query)


@router.get(
    "",
    response_model=Page[AssignmentListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_assignment",
    dependencies=[Depends(unique_query)],
)
async def list_assignments(
    company_id: uuid.UUID,
    query: Annotated[AssignmentQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[AssignmentListItem]:
    return await bom_assignments.list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/{object_id}",
    response_model=AssignmentDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_bom_assignment",
    dependencies=[Depends(no_query)],
)
async def get_assignment(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AssignmentDetail:
    return await bom_assignments.read(db, current, company_id, object_id)


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    body: AssignmentInput | AssignmentUpdate | ExpectedVersion,
    key: str,
    action: Literal["create", "update", "deactivate"],
    object_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await bom_assignments.command(
        request.app.state.session_factory, current, company, body, key, action, object_id
    )
    return command_response(request, result, created=action == "create")


@router.post(
    "",
    response_model=AssignmentDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_bom_assignment",
)
async def create_assignment(
    company_id: uuid.UUID,
    body: AssignmentInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "create")


@router.patch(
    "/{object_id}",
    response_model=AssignmentDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_bom_assignment",
)
async def update_assignment(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AssignmentUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "update", object_id)


@router.post(
    "/{object_id}/deactivate",
    response_model=AssignmentDetail,
    response_model_exclude_unset=True,
    operation_id="withdraw_catalog_bom_assignment",
)
async def deactivate_assignment(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "deactivate", object_id)
