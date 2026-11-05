"""Reusable warranty policy identities; coverage lives in immutable revisions."""

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
from catalog.schemas.units import ExpectedVersion
from catalog.schemas.warranties import (
    WarrantyPolicyCreate,
    WarrantyPolicyDetail,
    WarrantyPolicyListItem,
    WarrantyPolicyQuery,
    WarrantyPolicyUpdate,
)
from catalog.tasks.classification import list_rows, read
from catalog.tasks.profiles import WARRANTY_POLICY

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/warranty-policies",
    response_model=Page[WarrantyPolicyListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warranty_policy",
    dependencies=[Depends(unique_query)],
)
async def list_warranty_policy(
    company_id: uuid.UUID,
    query: Annotated[WarrantyPolicyQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        WARRANTY_POLICY,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/warranty-policies/{object_id}",
    response_model=WarrantyPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_warranty_policy",
)
async def get_warranty_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, WARRANTY_POLICY)


@router.post(
    "/warranty-policies",
    response_model=WarrantyPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_warranty_policy",
    status_code=201,
)
async def create_warranty_policy(
    company_id: uuid.UUID,
    body: WarrantyPolicyCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, WARRANTY_POLICY, body, idempotency_key, "create"
    )


@router.patch(
    "/warranty-policies/{object_id}",
    response_model=WarrantyPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_warranty_policy",
)
async def update_warranty_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: WarrantyPolicyUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        WARRANTY_POLICY,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/warranty-policies/{object_id}/activate",
    response_model=WarrantyPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_warranty_policy",
)
async def activate_warranty_policy(
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
        WARRANTY_POLICY,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/warranty-policies/{object_id}/deactivate",
    response_model=WarrantyPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_warranty_policy",
)
async def deactivate_warranty_policy(
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
        WARRANTY_POLICY,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
