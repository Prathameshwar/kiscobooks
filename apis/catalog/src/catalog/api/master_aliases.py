"""Protected Catalog master aliases through a closed owner registry."""

import uuid
from typing import Annotated, Literal

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
from catalog.schemas.master_references import (
    AliasCreate,
    AliasDetail,
    AliasListItem,
    AliasQuery,
    MasterEntity,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.master_reference_reads import list_rows, read, resolve
from catalog.tasks.master_references import ALIAS, command

router = APIRouter(
    prefix="/v1/companies/{company_id}/masters/{entity_type}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
    body: BaseModel,
    key: str,
    action: Literal["create", "activate", "deactivate"],
    object_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company,
        entity,
        target,
        ALIAS,
        key=key,
        body=body,
        action=action,
        object_id=object_id,
    )
    return command_response(request, result, created=action == "create")


@router.get(
    "/{target_id}/aliases",
    response_model=Page[AliasListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_master_alias",
    dependencies=[Depends(unique_query)],
)
async def listing(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
    query: Annotated[AliasQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        entity_type,
        target_id,
        ALIAS,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/{target_id}/aliases/{object_id}",
    response_model=AliasDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_master_alias",
)
async def get(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, entity_type, target_id, object_id, ALIAS)


@router.post(
    "/{target_id}/aliases",
    response_model=AliasDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_master_alias",
    status_code=201,
)
async def create(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
    body: AliasCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        entity_type,
        target_id,
        body,
        idempotency_key,
        "create",
    )


@router.post(
    "/{target_id}/aliases/{object_id}/activate",
    response_model=AliasDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_master_alias",
)
async def activate(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
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
        entity_type,
        target_id,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/{target_id}/aliases/{object_id}/deactivate",
    response_model=AliasDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_master_alias",
)
async def deactivate(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
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
        entity_type,
        target_id,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/aliases/resolve",
    response_model=AliasDetail,
    response_model_exclude_unset=True,
    operation_id="resolve_catalog_master_alias",
    dependencies=[Depends(unique_query)],
)
async def exact(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    query: Annotated[AliasCreate, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    return await resolve(db, current, company_id, entity_type, ALIAS, query.model_dump())
