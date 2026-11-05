"""Sales-channel master routes; a plain classification master.

Reads and writes go through the shared classification pipeline
(:func:`catalog.api.classification.write`, :func:`catalog.tasks.classification.read`,
:func:`~catalog.tasks.classification.list_rows`), which carries idempotency,
audit events, field policy and permission checks. Deactivation stays here as a
separate route rather than a boolean patch, matching the other masters.
"""

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
from catalog.schemas.sales_channel import (
    SalesChannelCreate,
    SalesChannelDetail,
    SalesChannelListItem,
    SalesChannelQuery,
    SalesChannelUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import list_rows, read
from catalog.tasks.profiles import SALES_CHANNEL

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/sales-channels",
    response_model=Page[SalesChannelListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_sales_channel",
    dependencies=[Depends(unique_query)],
)
async def list_sales_channels(
    company_id: uuid.UUID,
    query: Annotated[SalesChannelQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        SALES_CHANNEL,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/sales-channels/{object_id}",
    response_model=SalesChannelDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_sales_channel",
)
async def get_sales_channel(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, SALES_CHANNEL)


@router.post(
    "/sales-channels",
    response_model=SalesChannelDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_sales_channel",
    status_code=201,
)
async def create_sales_channel(
    company_id: uuid.UUID,
    body: SalesChannelCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, SALES_CHANNEL, body, idempotency_key, "create")


@router.patch(
    "/sales-channels/{object_id}",
    response_model=SalesChannelDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_sales_channel",
)
async def update_sales_channel(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: SalesChannelUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        SALES_CHANNEL,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/sales-channels/{object_id}/activate",
    response_model=SalesChannelDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_sales_channel",
)
async def activate_sales_channel(
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
        SALES_CHANNEL,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/sales-channels/{object_id}/deactivate",
    response_model=SalesChannelDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_sales_channel",
)
async def deactivate_sales_channel(
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
        SALES_CHANNEL,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
