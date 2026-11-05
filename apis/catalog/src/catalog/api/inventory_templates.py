"""Reusable inventory template identities; requirements live in revisions."""

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
from catalog.schemas.inventory_templates import (
    InventoryTemplateCreate,
    InventoryTemplateDetail,
    InventoryTemplateListItem,
    InventoryTemplateQuery,
    InventoryTemplateUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.profiles import INVENTORY_TEMPLATE

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/inventory-templates",
    response_model=Page[InventoryTemplateListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_inventory_template",
    dependencies=[Depends(unique_query)],
)
async def list_inventory_template(
    company_id: uuid.UUID,
    query: Annotated[InventoryTemplateQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        INVENTORY_TEMPLATE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/inventory-templates/{object_id}",
    response_model=InventoryTemplateDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_inventory_template",
)
async def get_inventory_template(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, INVENTORY_TEMPLATE)


@router.post(
    "/inventory-templates",
    response_model=InventoryTemplateDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_inventory_template",
    status_code=201,
)
async def create_inventory_template(
    company_id: uuid.UUID,
    body: InventoryTemplateCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, INVENTORY_TEMPLATE, body, idempotency_key, "create"
    )


@router.patch(
    "/inventory-templates/{object_id}",
    response_model=InventoryTemplateDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_inventory_template",
)
async def update_inventory_template(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: InventoryTemplateUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        INVENTORY_TEMPLATE,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/inventory-templates/{object_id}/activate",
    response_model=InventoryTemplateDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_inventory_template",
)
async def activate_inventory_template(
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
        INVENTORY_TEMPLATE,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/inventory-templates/{object_id}/deactivate",
    response_model=InventoryTemplateDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_inventory_template",
)
async def deactivate_inventory_template(
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
        INVENTORY_TEMPLATE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
