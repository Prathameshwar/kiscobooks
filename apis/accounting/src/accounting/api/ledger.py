"""Journal, source-ledger and balance HTTP contracts."""

import uuid
from typing import Annotated

from billing_platform.db.access import company_object
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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
from accounting.api.workflows import export_records
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.schemas.ledger import (
    Balance,
    BalanceQuery,
    JournalCreate,
    JournalDetail,
    JournalLineDetail,
    JournalLineListItem,
    JournalListItem,
    JournalPreview,
    JournalQuery,
    JournalReverse,
    JournalUpdate,
    JournalVoid,
)
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks import journal_drafts, journal_posting, ledger_reads
from accounting.tasks.access import authorize
from accounting.tasks.commands import protected
from accounting.tasks.reads import listing

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post("/journals/preview", response_model=JournalPreview)
async def preview(
    company_id: uuid.UUID,
    body: JournalCreate,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> JournalPreview:
    no_query(request)
    return await journal_drafts.preview(db, current, body)


@router.post(
    "/journals",
    response_model=JournalDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def create(
    company_id: uuid.UUID,
    body: JournalCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await journal_drafts.create(
            request.app.state.session_factory, current, body, idempotency_key
        ),
    )


@router.put(
    "/journals/{object_id}", response_model=JournalDetail, dependencies=[Depends(financial_rate)]
)
async def update(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: JournalUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await journal_drafts.update(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/journals/{object_id}/post",
    response_model=JournalDetail,
    dependencies=[Depends(financial_rate)],
)
async def post(
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
        await journal_posting.post(
            request.app.state.session_factory,
            current,
            object_id,
            body,
            idempotency_key,
            request.app.state.posting_client,
        ),
    )


@router.post(
    "/journals/{object_id}/void",
    response_model=JournalDetail,
    dependencies=[Depends(financial_rate)],
)
async def void(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: JournalVoid,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await journal_posting.void(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/journals/{object_id}/reversal",
    response_model=JournalDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def reversal(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: JournalReverse,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    result = await journal_posting.reversal(
        request.app.state.session_factory, current, object_id, body, idempotency_key
    )
    output = response(request, result)
    output.headers["Location"] = "../" + str(result.value.model_dump()["id"])
    return output


@router.get(
    "/journals",
    response_model=Page[JournalListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def journals(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[JournalQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        FINANCIAL_BY_NAME["journal"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        JournalListItem,
    )


@router.get(
    "/journals/{object_id}", response_model=JournalDetail, response_model_exclude_unset=True
)
async def journal(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = FINANCIAL_BY_NAME["journal"]
    authorize(current, spec, "read")
    return protected(
        await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/journal-lines",
    response_model=Page[JournalLineListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def lines(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[JournalQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        FINANCIAL_BY_NAME["journal_line"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        JournalLineListItem,
    )


@router.get(
    "/journal-lines/{object_id}",
    response_model=JournalLineDetail,
    response_model_exclude_unset=True,
)
async def line(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = FINANCIAL_BY_NAME["journal_line"]
    authorize(current, spec, "read")
    return protected(
        await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get("/ledger/balance", response_model=Balance, dependencies=[Depends(unique_query)])
async def balance(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[BalanceQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Balance:
    return await ledger_reads.balance(db, current, query)


@router.get(
    "/exports/journals",
    response_model=Page[JournalDetail],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def export_journals(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[JournalQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    return await export_records(company_id, "journals", request, query, current, db)


@router.get(
    "/exports/journal-lines",
    response_model=Page[JournalLineDetail],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def export_lines(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[JournalQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    return await export_records(company_id, "journal-lines", request, query, current, db)
