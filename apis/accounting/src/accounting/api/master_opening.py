"""Scoped held openings from master creation."""

import uuid
from typing import Annotated

from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import (
    ERROR_RESPONSES,
    Idempotency,
    no_query,
    response,
    session,
    unique_query,
)
from accounting.api.fiscal import financial_rate
from accounting.schemas.master_opening import (
    MasterOpeningCapture,
    MasterOpeningItem,
    MasterOpeningQuery,
)
from accounting.schemas.party_opening import PartyOpeningWithdraw
from accounting.tasks import master_opening as commands

router = APIRouter(
    prefix="/v1/companies/{company_id}/opening-batches/master-balances",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


@router.get("/capture", response_model=MasterOpeningCapture)
async def capture(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MasterOpeningCapture:
    no_query(request)
    return await commands.capture_metadata(db, current)


@router.get("", response_model=Page[MasterOpeningItem])
async def balances(
    company_id: uuid.UUID,
    query: Annotated[MasterOpeningQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[MasterOpeningItem]:
    return await commands.balances(
        db,
        current,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post(
    "/{object_id}/withdraw",
    response_model=MasterOpeningItem,
    dependencies=[Depends(financial_rate)],
)
async def withdraw(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PartyOpeningWithdraw,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await commands.withdraw(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )
