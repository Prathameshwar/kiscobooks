"""Native identifier profile authoring; no physical identifier ingestion."""

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
from catalog.schemas.profiles import (
    IdentifierProfileCreate,
    IdentifierProfileDetail,
    IdentifierProfileListItem,
    IdentifierProfileQuery,
    IdentifierProfileUpdate,
    IdentifierRequirementListItem,
    IdentifierRequirementQuery,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.identifier_policy import list_requirements
from catalog.tasks.profiles import IDENTIFIER_PROFILE

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/identifier-profiles",
    response_model=Page[IdentifierProfileListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_identifier_profile",
    dependencies=[Depends(unique_query)],
)
async def list_identifier_profile(
    company_id: uuid.UUID,
    query: Annotated[IdentifierProfileQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        IDENTIFIER_PROFILE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/identifier-profiles/{object_id}",
    response_model=IdentifierProfileDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_identifier_profile",
)
async def get_identifier_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, IDENTIFIER_PROFILE)


@router.post(
    "/identifier-profiles",
    response_model=IdentifierProfileDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_identifier_profile",
    status_code=201,
)
async def create_identifier_profile(
    company_id: uuid.UUID,
    body: IdentifierProfileCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, IDENTIFIER_PROFILE, body, idempotency_key, "create"
    )


@router.patch(
    "/identifier-profiles/{object_id}",
    response_model=IdentifierProfileDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_identifier_profile",
)
async def update_identifier_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: IdentifierProfileUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        IDENTIFIER_PROFILE,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/identifier-profiles/{object_id}/activate",
    response_model=IdentifierProfileDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_identifier_profile",
)
async def activate_identifier_profile(
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
        IDENTIFIER_PROFILE,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/identifier-profiles/{object_id}/deactivate",
    response_model=IdentifierProfileDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_identifier_profile",
)
async def deactivate_identifier_profile(
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
        IDENTIFIER_PROFILE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/identifier-profiles/{profile_id}/requirements",
    response_model=Page[IdentifierRequirementListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_identifier_profile_requirements",
    dependencies=[Depends(unique_query)],
)
async def requirements(
    company_id: uuid.UUID,
    profile_id: uuid.UUID,
    query: Annotated[IdentifierRequirementQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[IdentifierRequirementListItem]:
    return await list_requirements(
        db,
        current,
        company_id,
        profile_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
