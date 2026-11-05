"""Reviewed manual/CSV FX quotes and exact conversion previews."""

import datetime as dt
import uuid
from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.errors import NotFoundError
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, no_query, response, session, unique_query
from accounting.models.exchange_rates import ExchangeRateUsage
from accounting.schemas.exchange_rates import (
    Purpose,
    RateCandidate,
    RateContext,
    RateConversion,
    RateConversionView,
    RateDecision,
    RateImport,
    RateListItem,
    RateListQuery,
    RateUsageView,
    RateView,
)
from accounting.tasks import exchange_rates

router = APIRouter(prefix="/v1/companies/{company_id}/exchange-rates", responses=ERROR_RESPONSES)


@router.get("", response_model=Page[RateListItem], dependencies=[Depends(unique_query)])
async def list_quotes(
    company_id: uuid.UUID,
    request: Request,
    query: RateListQuery = Depends(),
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[RateListItem]:
    return await exchange_rates.listing(
        db,
        current,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get("/context", response_model=RateContext)
async def quote_context(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> RateContext:
    no_query(request)
    exchange_rates.authorize(current, False)
    return RateContext(
        company_id=company_id,
        base_currency=current.context.base_currency,
        allowed_currencies=sorted(current.context.allowed_currencies),
        multi_currency="multi_currency" in current.context.features,
    )


@router.get("/quotes/{quote_id}", response_model=RateView)
async def get_quote(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> RateView:
    exchange_rates.authorize(current, False)
    return exchange_rates.view(await exchange_rates.get(db, current, quote_id))


@router.get("/usages/{journal_line_id}", response_model=RateUsageView)
async def get_usage(
    company_id: uuid.UUID,
    journal_line_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> RateUsageView:
    current.actor.require_scope("ledger.read", target=ScopePath(company_id=company_id))
    usage = await db.scalar(
        select(ExchangeRateUsage).where(
            ExchangeRateUsage.company_id == company_id,
            ExchangeRateUsage.journal_line_id == journal_line_id,
        )
    )
    if usage is None:
        raise NotFoundError("exchange rate usage not found")
    return RateUsageView.model_validate(usage, from_attributes=True)


@router.post("/candidates", response_model=RateView, status_code=201)
async def candidate(
    company_id: uuid.UUID,
    body: RateCandidate,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ] = None,
) -> RateView | JSONResponse:
    no_query(request)
    if idempotency_key is not None:
        from accounting.tasks.exchange_rate_commands import command

        saved = await command(
            request.app.state.session_factory, current, body, idempotency_key, "create"
        )
        result = response(request, saved)
        result.headers["Location"] = "quotes/" + str(saved.value.model_dump()["id"])
        return result
    return await exchange_rates.candidate(db, current, body)


@router.post("/imports/csv", response_model=list[RateView], status_code=201)
async def import_csv(
    company_id: uuid.UUID,
    body: RateImport,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[RateView]:
    return await exchange_rates.import_csv(db, current, body)


@router.post("/{quote_id}/approve", response_model=RateView)
async def approve(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    body: RateDecision,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ] = None,
) -> RateView | JSONResponse:
    no_query(request)
    if idempotency_key is not None:
        from accounting.tasks.exchange_rate_commands import command

        return response(
            request,
            await command(
                request.app.state.session_factory,
                current,
                body,
                idempotency_key,
                "approve",
                quote_id,
            ),
        )
    return await exchange_rates.decide(db, current, quote_id, body, "approve")


@router.post("/{quote_id}/withdraw", response_model=RateView)
async def withdraw(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    body: RateDecision,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ] = None,
) -> RateView | JSONResponse:
    no_query(request)
    if idempotency_key is not None:
        from accounting.tasks.exchange_rate_commands import command

        return response(
            request,
            await command(
                request.app.state.session_factory,
                current,
                body,
                idempotency_key,
                "withdraw",
                quote_id,
            ),
        )
    return await exchange_rates.decide(db, current, quote_id, body, "withdraw")


@router.get("/effective", response_model=RateView)
async def effective(
    company_id: uuid.UUID,
    from_currency: str = Query(pattern=r"^[A-Z]{3}$"),
    purpose: Purpose = Query(),
    effective_date: dt.date = Query(),
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> RateView:
    return await exchange_rates.effective(db, current, from_currency, purpose, effective_date)


@router.post("/conversion-preview", response_model=RateConversionView)
async def conversion_preview(
    company_id: uuid.UUID,
    body: RateConversion,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> RateConversionView:
    return await exchange_rates.convert(db, current, body)
