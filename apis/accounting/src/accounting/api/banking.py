"""Manual bank instrument history, using owner field policies and signed keyset cursors."""

import uuid
from typing import Annotated, Any

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
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
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.voucher_money import BankInstrument, BankInstrumentEvent
from accounting.schemas.banking import (
    BankAdoptRequest,
    BankEventCommand,
    BankEventDetail,
    BankEventPage,
    BankEventRequest,
    BankHistoryQuery,
    BankInstrumentDetail,
    BankInstrumentPage,
    BankInstrumentQuery,
)
from accounting.tasks import banking
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.commands import protected

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


@router.get(
    "/bank-instruments", response_model=BankInstrumentPage, response_model_exclude_none=True
)
async def instruments(
    company_id: uuid.UUID,
    request: Request,
    filters: Annotated[BankInstrumentQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    from accounting.models.masters import Account
    from accounting.schemas.banking import BankInstrumentListItem

    account_id, date_from, date_to, limit, cursor = (
        filters.account_id,
        filters.date_from,
        filters.date_to,
        filters.limit,
        filters.cursor,
    )

    spec = FINANCIAL_BY_NAME["bank_instrument"]
    authorize(current, spec, "read")
    allowed = readable(current, spec)
    if (account_id and "account_id" not in allowed) or (
        (date_from or date_to) and "booking_date" not in allowed
    ):
        raise PermissionDeniedError("bank filter field is not readable")
    if date_from and date_to and date_from > date_to:
        raise ValidationFailedError("invalid bank date range")
    if account_id:
        await company_object(db, Account, account_id, company_id=company_id)
    codec = CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"bank-instruments:{current.actor.tenant_id}:{company_id}:{authority_fingerprint(current)}:{account_id}:{date_from}:{date_to}:{limit}",
    )
    fields = sorted(set(BankInstrumentListItem.model_fields) & allowed)
    query = select(*(getattr(BankInstrument, name) for name in fields)).where(
        BankInstrument.company_id == company_id
    )
    if account_id:
        query = query.where(BankInstrument.account_id == account_id)
    if date_from:
        query = query.where(BankInstrument.booking_date >= date_from)
    if date_to:
        query = query.where(BankInstrument.booking_date <= date_to)
    if cursor:
        try:
            after = uuid.UUID(codec.decode(cursor)["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationFailedError("invalid bank cursor") from error
        query = query.where(BankInstrument.id > after)
    rows = list((await db.execute(query.order_by(BankInstrument.id).limit(limit + 1))).mappings())
    return {
        "items": [dict(row) for row in rows[:limit]],
        "page": {
            "limit": limit,
            "has_more": len(rows) > limit,
            "next_cursor": codec.encode({"id": str(rows[limit - 1]["id"])})
            if len(rows) > limit
            else None,
        },
    }


@router.post(
    "/bank-instruments/adopt",
    response_model=BankInstrumentDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def adopt(
    company_id: uuid.UUID,
    body: BankAdoptRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await banking.adopt(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.get("/bank-instruments/{object_id}", response_model=BankInstrumentDetail)
async def instrument(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    spec = FINANCIAL_BY_NAME["bank_instrument"]
    authorize(current, spec, "read")
    row = await company_object(db, BankInstrument, object_id, company_id=company_id)
    return protected(row, spec, current)


@router.get(
    "/bank-instruments/{object_id}/events",
    response_model=BankEventPage,
    response_model_exclude_none=True,
)
async def history(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    filters: Annotated[BankHistoryQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    limit, cursor = filters.limit, filters.cursor
    spec = FINANCIAL_BY_NAME["bank_instrument_event"]
    authorize(current, spec, "read")
    await company_object(db, BankInstrument, object_id, company_id=company_id)
    if not {"id", "instrument_id"} <= readable(current, spec):
        raise PermissionDeniedError("bank history identity is not readable")
    import hashlib

    from billing_platform.idempotency import canonical_json

    permission_hash = hashlib.sha256(canonical_json(list(current.context.policies))).hexdigest()
    codec = CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"bank-history:{current.actor.tenant_id}:{company_id}:{current.actor.user_id}:{object_id}:{limit}:{permission_hash}",
    )
    query = select(BankInstrumentEvent).where(
        BankInstrumentEvent.company_id == company_id, BankInstrumentEvent.instrument_id == object_id
    )
    if cursor:
        try:
            after = uuid.UUID(codec.decode(cursor)["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationFailedError("invalid bank history cursor") from exc
        query = query.where(BankInstrumentEvent.id > after)
    rows = list(await db.scalars(query.order_by(BankInstrumentEvent.id).limit(limit + 1)))
    return {
        "items": [
            protected(row, spec, current).model_dump(mode="json", exclude_none=True)
            for row in rows[:limit]
        ],
        "page": {
            "limit": limit,
            "has_more": len(rows) > limit,
            "next_cursor": codec.encode({"id": str(rows[limit - 1].id)})
            if len(rows) > limit
            else None,
        },
    }


@router.post(
    "/bank-instruments/{object_id}/events",
    response_model=BankEventDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def record(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BankEventRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    command = BankEventCommand(**body.model_dump(), instrument_id=object_id)
    return response(
        request,
        await banking.record(request.app.state.session_factory, current, command, idempotency_key),
    )
