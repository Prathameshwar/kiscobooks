"""Opening declarations, evidence and native journal preparation; company scoped."""

import uuid
from typing import Annotated, Any

from billing_platform.db.access import company_object
from billing_platform.listing import ListQuery, Page
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field
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
from accounting.models.subledger import OpeningBatch
from accounting.schemas.financial_opening import (
    FinancialOpeningCapabilities,
    FinancialOpeningCaptureMetadata,
    FinancialOpeningExportTicket,
    FinancialOpeningPreview,
    FinancialOpeningReadiness,
    FinancialOpeningRevisionItem,
    OpeningDeclaration,
    OpeningEntry,
    OpeningEntryItem,
    OpeningEntryPostingLink,
    OpeningEntryQuery,
    OpeningJournalRecovery,
    OpeningReconciliation,
    OpeningReplace,
    OpeningRevisionCommand,
    OpeningWorkspaceDetail,
)
from accounting.schemas.masters import Input
from accounting.tasks import financial_opening as commands
from accounting.tasks import financial_opening_reads as reads

router = APIRouter(
    prefix="/v1/companies/{company_id}/opening-batches",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


class ExportQuery(Input):
    token: str = Field(min_length=1, max_length=4096)


def secret(request: Request) -> bytes:
    return str(request.app.state.settings.actor_signing_secret.get_secret_value()).encode()


@router.get("/readiness", response_model=FinancialOpeningReadiness)
async def readiness(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> FinancialOpeningReadiness:
    no_query(request)
    return await reads.readiness(db, current)


@router.get("/capabilities", response_model=FinancialOpeningCapabilities)
async def capabilities(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FinancialOpeningCapabilities:
    no_query(request)
    commands.require_read(current)
    return FinancialOpeningCapabilities(company_id=company_id)


@router.get("/workspaces/field-set", response_model=FinancialOpeningCaptureMetadata)
async def field_set(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> dict[str, Any]:
    no_query(request)
    commands.require_read(current)
    return {
        "schema_version": 1,
        "capture": OpeningDeclaration.model_json_schema(),
        "capture_permissions": commands.capture_permissions(current),
        "permission_sources": [
            "accounting.opening_batch",
            "accounting.journal",
            "accounting.journal_line",
            "accounting.open_item",
        ],
        "native_field_sets": [
            f"/v1/companies/{company_id}/finance/field-sets/{FINANCIAL_BY_NAME[name].path}"
            for name in ("opening_batch", "journal", "journal_line", "open_item")
        ],
        "posting_date_source": "company.books_begin_date",
    }


@router.post(
    "/workspaces/preview",
    response_model=FinancialOpeningPreview,
    dependencies=[Depends(financial_rate)],
)
async def preview(
    company_id: uuid.UUID,
    body: OpeningDeclaration,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> FinancialOpeningPreview:
    no_query(request)
    return await reads.preview(db, current, body)


@router.post(
    "/workspaces",
    response_model=OpeningWorkspaceDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def create(
    company_id: uuid.UUID,
    body: OpeningDeclaration,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await commands.create(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.get("/workspaces/{object_id}", response_model=OpeningWorkspaceDetail)
async def detail(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningWorkspaceDetail:
    no_query(request)
    return await commands.detail(db, current, object_id)


@router.get("/workspaces/{object_id}/declaration", response_model=OpeningDeclaration)
async def declaration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningDeclaration:
    no_query(request)
    commands.require_read(current)
    batch = await company_object(db, OpeningBatch, object_id, company_id=company_id)
    return await commands.declaration(db, current, batch)


@router.get("/workspaces/{object_id}/entries", response_model=Page[OpeningEntryItem])
async def entries(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[OpeningEntryQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[OpeningEntryItem]:
    return await reads.entries(db, current, object_id, query, secret(request))


@router.get("/workspaces/{object_id}/entries/{entry_id}", response_model=OpeningEntry)
async def entry(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    no_query(request)
    return await reads.entry(db, current, object_id, entry_id)


@router.get(
    "/workspaces/{object_id}/entries/{entry_id}/posting-link",
    response_model=OpeningEntryPostingLink,
)
async def posting_link(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningEntryPostingLink:
    no_query(request)
    return await reads.posting_link(db, current, object_id, entry_id)


@router.get("/workspaces/{object_id}/revisions", response_model=Page[FinancialOpeningRevisionItem])
async def revisions(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[ListQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[FinancialOpeningRevisionItem]:
    return await reads.revisions(db, current, object_id, query, secret(request))


@router.get("/workspaces/{object_id}/revisions/{revision_id}", response_model=OpeningDeclaration)
async def revision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningDeclaration:
    no_query(request)
    commands.require_read(current)
    batch = await company_object(db, OpeningBatch, object_id, company_id=company_id)
    return await commands.declaration(db, current, batch, revision_id)


@router.post(
    "/workspaces/{object_id}/replace",
    response_model=OpeningWorkspaceDetail,
    dependencies=[Depends(financial_rate)],
)
async def replace(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningReplace,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await commands.replace(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/workspaces/{object_id}/prepare-drafts",
    response_model=OpeningWorkspaceDetail,
    dependencies=[Depends(financial_rate)],
)
async def prepare(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningRevisionCommand,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await commands.execute(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/workspaces/{object_id}/finalize",
    response_model=OpeningWorkspaceDetail,
    dependencies=[Depends(financial_rate)],
)
async def finalize(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningRevisionCommand,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await commands.finalize(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/workspaces/{object_id}/void",
    response_model=OpeningWorkspaceDetail,
    dependencies=[Depends(financial_rate)],
)
async def void(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OpeningRevisionCommand,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await commands.void(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.get("/workspaces/{object_id}/reconciliation", response_model=OpeningReconciliation)
async def reconciliation(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningReconciliation:
    no_query(request)
    from accounting.tasks.financial_opening_reconciliation import reconcile

    return await reconcile(db, current, object_id)


@router.get(
    "/workspaces/{object_id}/journals/{journal_id}/recovery",
    response_model=OpeningJournalRecovery,
)
async def journal_recovery(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    journal_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningJournalRecovery:
    no_query(request)
    from accounting.tasks.financial_opening_recovery import recovery

    return await recovery(db, current, object_id, journal_id)


@router.get("/workspaces/{object_id}/export-ticket", response_model=FinancialOpeningExportTicket)
async def ticket(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> FinancialOpeningExportTicket:
    no_query(request)
    return await reads.ticket(db, current, object_id, secret(request))


@router.get("/workspaces/{object_id}/export")
async def export(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[ExportQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    return Response(
        await reads.export(db, current, object_id, query.token, secret(request)),
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="financial-opening.csv"',
        },
    )
