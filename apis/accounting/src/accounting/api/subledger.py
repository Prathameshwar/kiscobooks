"""Opening and debtor/creditor source workflow endpoints."""

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
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.resources import Resource
from accounting.schemas import subledger as schema
from accounting.schemas.fiscal import FiscalTransitionListItem
from accounting.schemas.ledger import BalanceQuery, BusinessDate
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks import allocations, openings, party_documents, subledger_reads
from accounting.tasks.access import authorize
from accounting.tasks.commands import protected
from accounting.tasks.reads import listing

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.get("/financial-setup/zero-opening-review", response_model=schema.ZeroOpeningReview)
async def review_initial_zero(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.ZeroOpeningReview:
    from accounting.tasks.zero_opening import review

    no_query(request)
    return await review(db, current)


@router.post(
    "/financial-setup/confirm-zero-opening",
    response_model=schema.OpeningBatchDetail,
    response_model_exclude_unset=True,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def confirm_initial_zero(
    company_id: uuid.UUID,
    body: schema.ZeroOpeningConfirm,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    from accounting.tasks.zero_opening import confirm

    no_query(request)
    return response(
        request, await confirm(request.app.state.session_factory, current, body, idempotency_key)
    )


@router.post("/opening-batches/preview", response_model=schema.OpeningPreview)
async def preview(
    company_id: uuid.UUID,
    body: schema.OpeningCreate,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.OpeningPreview:
    no_query(request)
    return await openings.preview(db, current, body)


@router.post(
    "/opening-batches",
    response_model=schema.OpeningBatchDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def opening(
    company_id: uuid.UUID,
    body: schema.OpeningCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await openings.create(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.post(
    "/opening-batches/{object_id}/finalize-zero",
    response_model=schema.OpeningBatchDetail,
    dependencies=[Depends(financial_rate)],
)
async def finalize_zero(
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
        await openings.finalize_zero(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/opening-batches/{object_id}/void",
    response_model=schema.OpeningBatchDetail,
    dependencies=[Depends(financial_rate)],
)
async def void_opening(
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
        await openings.void(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/source-documents",
    response_model=schema.SourceDocumentDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def source(
    company_id: uuid.UUID,
    body: schema.SourceCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await party_documents.create(
            request.app.state.session_factory, current, body, idempotency_key
        ),
    )


@router.post(
    "/allocations",
    response_model=schema.AllocationDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def allocation(
    company_id: uuid.UUID,
    body: schema.AllocationCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await allocations.create(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.post(
    "/allocations/{object_id}/reverse",
    response_model=schema.AllocationDetail,
    dependencies=[Depends(financial_rate)],
)
async def unallocate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.AllocationReverse,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await allocations.reverse(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.get("/subledger/ageing", response_model=schema.Ageing, dependencies=[Depends(unique_query)])
async def ageing(
    company_id: uuid.UUID,
    query: Annotated[schema.ItemQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.Ageing:
    return await subledger_reads.ageing(db, current, query)


@router.get(
    "/open-items/{object_id}/balance",
    response_model=schema.ItemBalance,
    dependencies=[Depends(unique_query)],
)
async def item_balance(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    as_of: BusinessDate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.ItemBalance:
    return await subledger_reads.item_balance(db, current, object_id, as_of)


def add_reads(spec: Resource, item_schema: type[BaseModel], *, target: APIRouter = router) -> None:
    async def collection(
        company_id: uuid.UUID,
        request: Request,
        query: Annotated[schema.FinanceQuery, Query()],
        current: Access = Depends(access),
        db: AsyncSession = Depends(session),
    ) -> Page[BaseModel]:
        return await listing(
            db,
            current,
            spec,
            query,
            request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
            item_schema,
        )

    async def detail(
        company_id: uuid.UUID,
        object_id: uuid.UUID,
        request: Request,
        current: Access = Depends(access),
        db: AsyncSession = Depends(session),
    ) -> BaseModel:
        no_query(request)
        authorize(current, spec, "read")
        return protected(
            await company_object(db, spec.model, object_id, company_id=company_id), spec, current
        )

    async def export(
        company_id: uuid.UUID,
        request: Request,
        query: Annotated[schema.FinanceQuery, Query()],
        current: Access = Depends(access),
        db: AsyncSession = Depends(session),
    ) -> JSONResponse:
        from accounting.api.workflows import export_records

        return await export_records(company_id, spec.path, request, query, current, db)

    target.add_api_route(
        "/exports/" + spec.path,
        export,
        methods=["GET"],
        response_model=Page.__class_getitem__(spec.detail),
        response_model_exclude_unset=True,
        dependencies=[Depends(unique_query)],
        name=f"export_{spec.name}",
    )
    target.add_api_route(
        "/" + spec.path,
        collection,
        methods=["GET"],
        response_model=Page.__class_getitem__(item_schema),
        response_model_exclude_unset=True,
        dependencies=[Depends(unique_query)],
        name=f"list_{spec.name}",
    )
    target.add_api_route(
        "/" + spec.path + "/{object_id}",
        detail,
        methods=["GET"],
        response_model=spec.detail,
        response_model_exclude_unset=True,
        name=f"get_{spec.name}",
    )


for name, item in (
    ("fiscal_transition", FiscalTransitionListItem),
    ("opening_batch", schema.OpeningBatchListItem),
    ("source_document", schema.SourceDocumentListItem),
    ("open_item", schema.OpenItemListItem),
    ("allocation", schema.AllocationListItem),
):
    add_reads(FINANCIAL_BY_NAME[name], item)


@router.get(
    "/subledger/reconciliation",
    response_model=schema.Reconciliation,
    dependencies=[Depends(unique_query)],
)
async def reconciliation(
    company_id: uuid.UUID,
    query: Annotated[BalanceQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.Reconciliation:
    from accounting.tasks.reconciliation import account

    return await account(db, current, query)


@router.post(
    "/opening-batches/{object_id}/reopen-zero",
    response_model=schema.OpeningBatchDetail,
    dependencies=[Depends(financial_rate)],
)
async def reopen_zero(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.OpeningReopen,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await openings.reopen_zero(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )
