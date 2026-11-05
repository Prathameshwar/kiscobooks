"""Company-scoped opening APIs; execution remains the native voucher owner path."""

import uuid
from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope
from billing_platform.listing import ListQuery, Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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
from accounting.api.stock import selection_source
from accounting.models.masters import AccountingSetup
from accounting.models.stock import StockPosting
from accounting.schemas.query import FieldSet
from accounting.schemas.stock_opening import (
    OpeningAccountingPreview,
    OpeningCalculate,
    OpeningCalculated,
    OpeningCapabilities,
    OpeningCohort,
    OpeningCohortQuery,
    OpeningControlDetail,
    OpeningExportQuery,
    OpeningExportTicket,
    OpeningFinalize,
    OpeningManifest,
    OpeningReadiness,
    OpeningReplace,
    OpeningRevisionItem,
    OpeningZeroConfirm,
)
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.stock_opening_calculation import preview
from accounting.tasks.stock_opening_control import (
    confirm_zero,
    control,
    detail,
    finalize,
    pending,
    register,
    require_access,
    require_capture_read,
    revise_control,
)


def opening_limit(request: Request, current: Access = Depends(access)) -> None:
    if request.method == "POST" and not request.app.state.write_limiter.allow(
        f"sopen:{current.actor.tenant_id}:{current.context.company_id}:{current.actor.user_id}",
        limit=30,
    ):
        raise HTTPException(status_code=429, detail="opening request rate limit exceeded")


router = APIRouter(
    prefix="/v1/companies/{company_id}/stock/openings",
    responses=ERROR_RESPONSES | {429: {"model": ErrorEnvelope}},
    dependencies=[Depends(unique_query), Depends(opening_limit)],
)


@router.post("/calculate", response_model=OpeningCalculated)
async def calculate(
    company_id: uuid.UUID,
    body: OpeningCalculate,
    request: Request,
    current: Access = Depends(access),
) -> OpeningCalculated:
    no_query(request)
    proof, source = selection_source(request)
    with tenant_scope(current.actor.tenant_id):
        return await preview(current, body, proof, source)


@router.get("/readiness", response_model=OpeningReadiness)
async def readiness(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningReadiness:
    no_query(request)
    require_access(current)
    row = await control(db, company_id)
    legacy = (
        await db.scalar(
            select(StockPosting.id).where(StockPosting.company_id == company_id).limit(1)
        )
        if row is None
        else None
    )
    blockers = (
        []
        if row and row.status == "FINALIZED"
        else ["LEGACY_ACTIVITY_REQUIRES_REVIEW"]
        if legacy
        else ["OPENING_NOT_FINALIZED"]
    )
    from accounting.models.fiscal import FiscalPeriod
    from accounting.models.stock import StockAccountPolicy
    from accounting.models.subledger import OpeningBatch

    finance = financial_context(current)
    setup_generation = await db.scalar(
        select(AccountingSetup.generation).where(AccountingSetup.company_id == company_id)
    )
    if setup_generation is None:
        blockers.append("ACCOUNTING_NOT_INITIALIZED")
    if not request.app.state.settings.voucher_stock_enabled:
        blockers.append("STOCK_POSTING_NOT_ENABLED")
    execution_pending = await pending(db, company_id)
    if execution_pending:
        blockers.append("EXECUTION_UNCONFIRMED")
    period = list(
        await db.scalars(
            select(FiscalPeriod.status)
            .where(
                FiscalPeriod.company_id == company_id,
                FiscalPeriod.start_date <= finance.books_begin_date,
                FiscalPeriod.end_date >= finance.books_begin_date,
            )
            .limit(2)
        )
    )
    if period != ["OPEN"]:
        blockers.append("BOOKS_BEGIN_PERIOD_NOT_OPEN")
    later_closed = await db.scalar(
        select(FiscalPeriod.id)
        .where(
            FiscalPeriod.company_id == company_id,
            FiscalPeriod.end_date >= finance.books_begin_date,
            FiscalPeriod.status.in_(("CLOSED", "LOCKED")),
        )
        .limit(1)
    )
    if later_closed:
        blockers.append("LATER_BOOKS_CLOSED")
    if not await db.scalar(
        select(OpeningBatch.id)
        .where(OpeningBatch.company_id == company_id, OpeningBatch.status == "FINALIZED")
        .limit(1)
    ):
        blockers.append("FINANCIAL_OPENING_NOT_FINALIZED")
    if not await db.scalar(
        select(StockAccountPolicy.id)
        .where(
            StockAccountPolicy.company_id == company_id,
            StockAccountPolicy.valid_from <= finance.books_begin_date,
            (StockAccountPolicy.valid_to.is_(None))
            | (StockAccountPolicy.valid_to >= finance.books_begin_date),
        )
        .limit(1)
    ):
        blockers.append("STOCK_ACCOUNTS_NOT_CONFIGURED")
    target = ScopePath(company_id=company_id)
    can_start = (
        row is None
        and legacy is None
        and setup_generation is not None
        and period == ["OPEN"]
        and not later_closed
        and not execution_pending
        and all(
            current.actor.allows_scope(key, target=target)
            for key in ("accounting.finance.manage", "accounting.stock.configure", "period.post")
        )
    )
    return OpeningReadiness(
        company_id=company_id,
        books_begin_date=financial_context(current).books_begin_date,
        control_id=row.id if row else None,
        status=row.status if row else "LEGACY_ACTIVITY" if legacy else "NOT_STARTED",
        blockers=blockers,
        can_start=can_start,
        posting_enabled=request.app.state.settings.voucher_stock_enabled,
        expected_generation=setup_generation,
        can_confirm_zero=row is None
        and legacy is None
        and setup_generation is not None
        and period == ["OPEN"]
        and not later_closed
        and not execution_pending
        and any(
            current.actor.allows_scope(key, target=target)
            for key in ("opening_balance.initialize_zero", "accounting.finance.manage")
        ),
    )


@router.get("/capture-fields", response_model=FieldSet)
async def capture_fields(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    """Opening capture uses posting authority, independent of read-only ledger pages."""
    from billing_platform.field_policy import denied_fields

    from accounting.stock_resources import STOCK_MOVEMENT
    from accounting.tasks.access import rules
    from accounting.tasks.reads import field_set

    no_query(request)
    require_access(current)
    metadata = field_set(current, STOCK_MOVEMENT)
    target = ScopePath(company_id=company_id)
    allowed = all(
        current.actor.allows_scope(permission, target=target)
        for permission in (
            "accounting.stock.configure",
            "accounting.finance.manage",
            "accounting.stock.post",
            "period.post",
        )
    )
    denied = denied_fields(
        STOCK_MOVEMENT.create.model_fields,
        rules=rules(current, STOCK_MOVEMENT, None),
        access="write",
        target=target,
    )
    return metadata.model_copy(
        update={
            "fields": [
                field.model_copy(
                    update={
                        "writable": allowed and field.key not in denied,
                    }
                )
                for field in metadata.fields
            ]
        }
    )


@router.get("/capabilities", response_model=OpeningCapabilities)
async def capabilities(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> OpeningCapabilities:
    no_query(request)
    require_access(current)
    return OpeningCapabilities(
        company_id=company_id,
        posting_enabled=request.app.state.settings.voucher_stock_enabled,
        valuation_methods=["FIFO", "MOVING_AVERAGE"],
    )


@router.post("", response_model=OpeningControlDetail, status_code=201)
async def create(
    company_id: uuid.UUID,
    body: OpeningManifest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await register(request.app.state.session_factory, current, body, idempotency_key),
        )


@router.post("/confirm-zero", response_model=OpeningControlDetail, status_code=201)
async def zero(
    company_id: uuid.UUID,
    body: OpeningZeroConfirm,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await confirm_zero(request.app.state.session_factory, current, body, idempotency_key),
        )


@router.post("/products/{item_id}", response_model=OpeningControlDetail, status_code=201)
async def create_product_opening(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: OpeningManifest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await register(
                request.app.state.session_factory, current, body, idempotency_key, item_id=item_id
            ),
        )


@router.post("/adopt", response_model=OpeningControlDetail, status_code=201)
async def adopt(
    company_id: uuid.UUID,
    body: OpeningManifest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await revise_control(
                request.app.state.session_factory, current, None, "adopt", body, idempotency_key
            ),
        )


@router.post("/{object_id}/reopen", response_model=OpeningControlDetail)
async def reopen(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningFinalize,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await revise_control(
                request.app.state.session_factory,
                current,
                object_id,
                "reopen",
                body,
                idempotency_key,
            ),
        )


@router.post("/{object_id}/replace", response_model=OpeningControlDetail)
async def replace(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningReplace,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await revise_control(
                request.app.state.session_factory,
                current,
                object_id,
                "replace",
                body,
                idempotency_key,
            ),
        )


@router.get("/{object_id}", response_model=OpeningControlDetail)
async def get(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningControlDetail:
    from billing_platform.db.access import company_object

    from accounting.models.stock_opening import StockOpeningControl

    no_query(request)
    row = await company_object(db, StockOpeningControl, object_id, company_id=company_id)
    return await detail(db, current, row)


@router.get("/{object_id}/manifest", response_model=OpeningManifest)
async def manifest(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningManifest:
    from billing_platform.db.access import company_object

    from accounting.models.stock_opening import StockOpeningControl

    no_query(request)
    require_capture_read(current)
    row = await company_object(db, StockOpeningControl, object_id, company_id=company_id)
    return OpeningManifest.model_validate(row.manifest)


@router.get("/{object_id}/export-ticket", response_model=OpeningExportTicket)
async def export_ticket(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningExportTicket:
    from accounting.tasks.stock_opening_export import authorized, codec

    no_query(request)
    row = await authorized(db, current, object_id)
    token = codec(
        current, row, request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    ).encode({"id": str(object_id)})
    return OpeningExportTicket(
        token=token,
        expires_in=300,
        download_path=f"/v1/companies/{company_id}/stock/openings/{object_id}/export?token={token}",
    )


@router.get("/{object_id}/accounting-preview", response_model=OpeningAccountingPreview)
async def accounting_preview(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningAccountingPreview:
    from accounting.tasks.stock_opening_reads import accounting_preview as read_preview

    no_query(request)
    return await read_preview(db, current, object_id)


@router.get("/{object_id}/export", response_class=Response)
async def export(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[OpeningExportQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    from accounting.tasks.stock_opening_export import authorized, document

    row = await authorized(db, current, object_id)
    content = await document(
        db,
        current,
        row,
        query.token,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return Response(
        content,
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="opening-manifest.csv"',
        },
    )


@router.get("/{object_id}/cohorts", response_model=Page[OpeningCohort])
async def cohorts(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[OpeningCohortQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[OpeningCohort]:
    from accounting.tasks.stock_opening_reads import cohorts as read_cohorts

    return await read_cohorts(
        db,
        current,
        object_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get("/{object_id}/revisions", response_model=Page[OpeningRevisionItem])
async def revisions(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[ListQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[OpeningRevisionItem]:
    from accounting.tasks.stock_opening_reads import revisions as read_revisions

    return await read_revisions(
        db,
        current,
        object_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get("/{object_id}/revisions/{revision_id}", response_model=OpeningManifest)
async def revision_manifest(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningManifest:
    from billing_platform.db.access import company_object
    from billing_platform.errors import NotFoundError

    from accounting.models.stock_opening import StockOpeningControl, StockOpeningRevision

    no_query(request)
    require_capture_read(current)
    await company_object(db, StockOpeningControl, object_id, company_id=company_id)
    row = await company_object(db, StockOpeningRevision, revision_id, company_id=company_id)
    if row.control_id != object_id:
        raise NotFoundError("opening revision not found")
    return OpeningManifest.model_validate(row.manifest)


@router.get("/{object_id}/reconciliation", response_model=OpeningControlDetail)
async def reconciliation(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningControlDetail:
    from billing_platform.db.access import company_object
    from billing_platform.errors import ConflictError

    from accounting.models.stock_opening import StockOpeningControl
    from accounting.tasks.stock_reconciliation import assert_physical, assert_value_control

    no_query(request)
    row = await company_object(db, StockOpeningControl, object_id, company_id=company_id)
    review = await detail(db, current, row)
    for check, blocker in (
        (assert_physical, "PHYSICAL_RECONCILIATION_FAILED"),
        (assert_value_control, "GL_RECONCILIATION_FAILED"),
    ):
        try:
            await check(db, company_id)
        except ConflictError:
            review.blockers.append(blocker)
    return review


@router.post("/{object_id}/finalize", response_model=OpeningControlDetail)
async def finish(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningFinalize,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        return response(
            request,
            await finalize(
                request.app.state.session_factory, current, object_id, body, idempotency_key
            ),
        )
