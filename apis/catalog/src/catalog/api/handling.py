"""Reusable handling policy identities; coverage lives in immutable revisions."""

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
from catalog.schemas.handling import (
    HandlingProfileCreate,
    HandlingProfileDetail,
    HandlingProfileListItem,
    HandlingProfileQuery,
    HandlingProfileUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.profiles import HANDLING_PROFILE

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/handling-profiles",
    response_model=Page[HandlingProfileListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_handling_profile",
    dependencies=[Depends(unique_query)],
)
async def list_handling_profile(
    company_id: uuid.UUID,
    query: Annotated[HandlingProfileQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        HANDLING_PROFILE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/handling-profiles/{object_id}",
    response_model=HandlingProfileDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_handling_profile",
)
async def get_handling_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, HANDLING_PROFILE)


@router.post(
    "/handling-profiles",
    response_model=HandlingProfileDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_handling_profile",
    status_code=201,
)
async def create_handling_profile(
    company_id: uuid.UUID,
    body: HandlingProfileCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, HANDLING_PROFILE, body, idempotency_key, "create"
    )


@router.patch(
    "/handling-profiles/{object_id}",
    response_model=HandlingProfileDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_handling_profile",
)
async def update_handling_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: HandlingProfileUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        HANDLING_PROFILE,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/handling-profiles/{object_id}/activate",
    response_model=HandlingProfileDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_handling_profile",
)
async def activate_handling_profile(
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
        HANDLING_PROFILE,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/handling-profiles/{object_id}/deactivate",
    response_model=HandlingProfileDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_handling_profile",
)
async def deactivate_handling_profile(
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
        HANDLING_PROFILE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
