"""Attribute template revisions use the common revision command/history pipeline."""

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
from catalog.schemas.attributes import (
    AttributeMemberListItem,
    AttributeMemberQuery,
    AttributeSetRevisionCreate,
    AttributeSetRevisionDetail,
    AttributeSetRevisionListItem,
    AttributeSetRevisionQuery,
    AttributeSetRevisionUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.attribute_sets import list_members
from catalog.tasks.commercial_history import SET_REVISION, list_rows, read

router = APIRouter(
    prefix="/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "",
    response_model=Page[AttributeSetRevisionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_attribute_set_revisions",
    dependencies=[Depends(unique_query)],
)
async def revisions(
    company_id: uuid.UUID,
    attribute_set_id: uuid.UUID,
    query: Annotated[AttributeSetRevisionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        SET_REVISION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        attribute_set_id,
    )


@router.get(
    "/{object_id}",
    response_model=AttributeSetRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_attribute_set_revision",
)
async def revision(
    company_id: uuid.UUID,
    attribute_set_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, SET_REVISION, attribute_set_id)


@router.post(
    "",
    response_model=AttributeSetRevisionDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_attribute_set_revision",
)
async def create_revision(
    company_id: uuid.UUID,
    attribute_set_id: uuid.UUID,
    body: AttributeSetRevisionCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        SET_REVISION,
        body,
        idempotency_key,
        "create",
        None,
        attribute_set_id,
    )


@router.put(
    "/{object_id}/members",
    response_model=AttributeSetRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="replace_catalog_attribute_set_members",
)
async def replace_revision_members(
    company_id: uuid.UUID,
    attribute_set_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AttributeSetRevisionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        SET_REVISION,
        body,
        idempotency_key,
        "update",
        object_id,
        attribute_set_id,
    )


@router.post(
    "/{object_id}/publish",
    response_model=AttributeSetRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="publish_catalog_attribute_set_revision",
)
async def publish_revision(
    company_id: uuid.UUID,
    attribute_set_id: uuid.UUID,
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
        SET_REVISION,
        body,
        idempotency_key,
        "publish",
        object_id,
        attribute_set_id,
    )


@router.get(
    "/{object_id}/members",
    response_model=Page[AttributeMemberListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_attribute_set_members",
    dependencies=[Depends(unique_query)],
)
async def revision_members(
    company_id: uuid.UUID,
    attribute_set_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AttributeMemberQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[AttributeMemberListItem]:
    return await list_members(
        db,
        current,
        company_id,
        attribute_set_id,
        object_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
