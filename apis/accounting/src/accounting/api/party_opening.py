"""Opening balances held from party imports until the opening declaration takes them."""

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
from accounting.schemas.party_opening import (
    PartyOpeningItem,
    PartyOpeningQuery,
    PartyOpeningWithdraw,
)
from accounting.tasks import party_opening as commands

router = APIRouter(
    prefix="/v1/companies/{company_id}/opening-batches/party-balances",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


def secret(request: Request) -> bytes:
    return str(request.app.state.settings.actor_signing_secret.get_secret_value()).encode()


@router.get("", response_model=Page[PartyOpeningItem])
async def held_balances(
    company_id: uuid.UUID,
    query: Annotated[PartyOpeningQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[PartyOpeningItem]:
    return await commands.balances(db, current, query, secret(request))


@router.post(
    "/{object_id}/withdraw",
    response_model=PartyOpeningItem,
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
