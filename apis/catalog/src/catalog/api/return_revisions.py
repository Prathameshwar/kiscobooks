"""Return definitions reuse the common revision command and history pipeline."""

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
from catalog.api.commercial_history import write
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.schemas.returns import (
    ReturnConditionListItem,
    ReturnConditionQuery,
    ReturnRevisionDetail,
    ReturnRevisionInput,
    ReturnRevisionListItem,
    ReturnRevisionQuery,
    ReturnRevisionUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.commercial_history import RETURN_REVISION, list_rows, read
from catalog.tasks.return_conditions import list_conditions

router = APIRouter(
    prefix="/v1/companies/{company_id}/return-policies/{policy_id}/revisions",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "",
    response_model=Page[ReturnRevisionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_return_policy_revisions",
    dependencies=[Depends(unique_query)],
)
async def revisions(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    query: Annotated[ReturnRevisionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        RETURN_REVISION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        policy_id,
    )


@router.get(
    "/{object_id}",
    response_model=ReturnRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_return_policy_revision",
)
async def revision(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, RETURN_REVISION, policy_id)


@router.post(
    "",
    response_model=ReturnRevisionDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_return_policy_revision",
)
async def create_revision(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    body: ReturnRevisionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        RETURN_REVISION,
        body,
        idempotency_key,
        "create",
        None,
        policy_id,
    )


@router.patch(
    "/{object_id}",
    response_model=ReturnRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_return_policy_revision",
)
async def update_revision(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ReturnRevisionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        RETURN_REVISION,
        body,
        idempotency_key,
        "update",
        object_id,
        policy_id,
    )


@router.post(
    "/{object_id}/publish",
    response_model=ReturnRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="publish_catalog_return_policy_revision",
)
async def publish_revision(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
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
        RETURN_REVISION,
        body,
        idempotency_key,
        "publish",
        object_id,
        policy_id,
    )


@router.get(
    "/{object_id}/conditions",
    response_model=Page[ReturnConditionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_return_policy_conditions",
    dependencies=[Depends(unique_query)],
)
async def revision_conditions(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[ReturnConditionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[ReturnConditionListItem]:
    return await list_conditions(
        db,
        current,
        company_id,
        policy_id,
        object_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
