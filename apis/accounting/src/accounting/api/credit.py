"""Credit checks, reservation lifecycle and separate exception approval."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, Idempotency, no_query, response, session
from accounting.api.fiscal import financial_rate
from accounting.api.subledger import add_reads
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.schemas import credit as schema
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks import credit

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post("/credit/check", response_model=schema.CreditDecision)
async def check(
    company_id: uuid.UUID,
    body: schema.CreditCheck,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.CreditDecision:
    no_query(request)
    return await credit.assess(db, current, body)


@router.post(
    "/credit-reservations",
    response_model=schema.CreditReservationDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def reserve(
    company_id: uuid.UUID,
    body: schema.CreditRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await credit.reserve(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.post(
    "/credit-reservations/{object_id}/release",
    response_model=schema.CreditReservationDetail,
    dependencies=[Depends(financial_rate)],
)
async def release(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await credit.release(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/credit-reservations/{object_id}/renew",
    response_model=schema.CreditReservationDetail,
    dependencies=[Depends(financial_rate)],
)
async def renew(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.ReservationRenew,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await credit.renew(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/credit-overrides",
    response_model=schema.CreditOverrideDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def request_override(
    company_id: uuid.UUID,
    body: schema.OverrideRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await credit.request_override(
            request.app.state.session_factory, current, body, idempotency_key
        ),
    )


@router.post(
    "/credit-overrides/{object_id}/approve",
    response_model=schema.CreditOverrideDetail,
    dependencies=[Depends(financial_rate)],
)
async def approve_override(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.OverrideApprove,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await credit.approve_override(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


add_reads(FINANCIAL_BY_NAME["credit_reservation"], schema.CreditReservationListItem, target=router)
add_reads(FINANCIAL_BY_NAME["credit_override"], schema.CreditOverrideListItem, target=router)
