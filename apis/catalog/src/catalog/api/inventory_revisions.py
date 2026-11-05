"""Inventory requirements reuse the common revision command and history pipeline."""

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
from catalog.schemas.inventory_templates import (
    InventoryRevisionDetail,
    InventoryRevisionInput,
    InventoryRevisionListItem,
    InventoryRevisionQuery,
    InventoryRevisionUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.commercial_history import INVENTORY_REVISION, list_rows, read

router = APIRouter(
    prefix="/v1/companies/{company_id}/inventory-templates/{template_id}/revisions",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "",
    response_model=Page[InventoryRevisionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_inventory_template_revisions",
    dependencies=[Depends(unique_query)],
)
async def revisions(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    query: Annotated[InventoryRevisionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        INVENTORY_REVISION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        template_id,
    )


@router.get(
    "/{object_id}",
    response_model=InventoryRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_inventory_template_revision",
)
async def revision(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, INVENTORY_REVISION, template_id)


@router.post(
    "",
    response_model=InventoryRevisionDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_inventory_template_revision",
)
async def create_revision(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    body: InventoryRevisionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        INVENTORY_REVISION,
        body,
        idempotency_key,
        "create",
        None,
        template_id,
    )


@router.patch(
    "/{object_id}",
    response_model=InventoryRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_inventory_template_revision",
)
async def update_revision(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    object_id: uuid.UUID,
    body: InventoryRevisionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        INVENTORY_REVISION,
        body,
        idempotency_key,
        "update",
        object_id,
        template_id,
    )


@router.post(
    "/{object_id}/publish",
    response_model=InventoryRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="publish_catalog_inventory_template_revision",
)
async def publish_revision(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
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
        INVENTORY_REVISION,
        body,
        idempotency_key,
        "publish",
        object_id,
        template_id,
    )
