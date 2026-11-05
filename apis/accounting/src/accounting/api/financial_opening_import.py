"""Versioned financial opening imports; preparation and native posting stay separate."""

import uuid
from typing import Annotated, Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request, Response
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
from accounting.api.financial_opening import ExportQuery, secret
from accounting.api.fiscal import financial_rate
from accounting.domain.financial_opening_import import MARKER, OPTIONAL, REQUIRED
from accounting.models.financial_opening import FinancialOpeningImport
from accounting.schemas.financial_opening import FinancialOpeningExportTicket, OpeningDeclaration
from accounting.schemas.financial_opening_import import (
    FinancialOpeningImportCommit,
    FinancialOpeningImportDetail,
    FinancialOpeningImportItem,
    FinancialOpeningImportQuery,
    FinancialOpeningImportStage,
)
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks import financial_opening_import as tasks
from accounting.tasks.access import authority_fingerprint
from accounting.tasks.financial_opening import audit, require_read

router = APIRouter(
    prefix="/v1/companies/{company_id}/financial-opening-imports",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


@router.get("/template")
async def template(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> dict[str, Any]:
    no_query(request)
    require_read(current)
    return {
        "marker": MARKER,
        "version": 1,
        "required_columns": REQUIRED,
        "optional_columns": OPTIONAL,
        "formats": ["JSON", "CSV", "TSV", "XLSX"],
        "maximum_file_bytes": 2097152,
        "maximum_file_rows": 2000,
        "reference_policy": "Use exact authorized native account IDs. Names are not guessed.",
        "effect": (
            "Prepares a company declaration and native opening drafts. "
            "Post, confirm and finalize separately."
        ),
    }


@router.get("", response_model=Page[FinancialOpeningImportItem])
async def listing(
    company_id: uuid.UUID,
    query: Annotated[FinancialOpeningImportQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[FinancialOpeningImportItem]:
    require_read(current)
    if query.q:
        raise ValidationFailedError("use the typed import-state filter")
    statement = select(
        *(
            getattr(FinancialOpeningImport, key).label(key)
            for key in FinancialOpeningImportItem.model_fields
        )
    ).where(FinancialOpeningImport.company_id == company_id)
    if query.state:
        statement = statement.where(FinancialOpeningImport.state == query.state)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(FinancialOpeningImport.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "financial-opening-imports",
            "tenant": str(current.actor.tenant_id),
            "company": str(company_id),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret(request), context=context),
        project=lambda row: FinancialOpeningImportItem.model_validate(dict(row)),
    )


@router.post(
    "",
    response_model=FinancialOpeningImportDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def stage(
    company_id: uuid.UUID,
    body: FinancialOpeningImportStage,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await tasks.stage(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.get("/{object_id}", response_model=FinancialOpeningImportDetail)
async def detail(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> FinancialOpeningImportDetail:
    no_query(request)
    return await tasks.detail(db, current, object_id)


@router.get("/{object_id}/declaration", response_model=OpeningDeclaration)
async def captured_declaration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningDeclaration:
    """Private retained source for human review before committing an import."""
    no_query(request)
    require_read(current)
    row = await company_object(db, FinancialOpeningImport, object_id, company_id=company_id)
    return OpeningDeclaration.model_validate(row.document)


@router.post(
    "/{object_id}/validate",
    response_model=FinancialOpeningImportDetail,
    dependencies=[Depends(financial_rate)],
)
async def validate(
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
        await tasks.action(
            request.app.state.session_factory, current, object_id, body, idempotency_key, "validate"
        ),
    )


@router.post(
    "/{object_id}/commit",
    response_model=FinancialOpeningImportDetail,
    dependencies=[Depends(financial_rate)],
)
async def commit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: FinancialOpeningImportCommit,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await tasks.action(
            request.app.state.session_factory, current, object_id, body, idempotency_key, "commit"
        ),
    )


@router.post(
    "/{object_id}/prepare-drafts",
    response_model=FinancialOpeningImportDetail,
    dependencies=[Depends(financial_rate)],
)
async def prepare(
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
        await tasks.action(
            request.app.state.session_factory,
            current,
            object_id,
            body,
            idempotency_key,
            "prepare-drafts",
        ),
    )


@router.post(
    "/{object_id}/cancel",
    response_model=FinancialOpeningImportDetail,
    dependencies=[Depends(financial_rate)],
)
async def cancel(
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
        await tasks.action(
            request.app.state.session_factory, current, object_id, body, idempotency_key, "cancel"
        ),
    )


async def report_codec(
    db: AsyncSession, current: Access, object_id: uuid.UUID, request: Request
) -> CursorCodec:
    require_read(current)
    current.actor.require_scope(
        "accounting.export.read", target=ScopePath(company_id=current.context.company_id)
    )
    row = await company_object(
        db, FinancialOpeningImport, object_id, company_id=current.context.company_id
    )
    return CursorCodec(
        secret(request),
        ttl_seconds=300,
        context=canonical_json(
            {
                "resource": "financial-opening-import-report",
                "tenant": str(current.actor.tenant_id),
                "company": str(row.company_id),
                "actor": str(current.actor.user_id),
                "job": str(row.id),
                "version": row.row_version,
                "authority": authority_fingerprint(current),
            }
        ).decode(),
    )


@router.get("/{object_id}/report-ticket", response_model=FinancialOpeningExportTicket)
async def ticket(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> FinancialOpeningExportTicket:
    no_query(request)
    token = (await report_codec(db, current, object_id, request)).encode({"id": str(object_id)})
    return FinancialOpeningExportTicket(
        token=token,
        download_path=(
            f"/v1/companies/{company_id}/financial-opening-imports/"
            f"{object_id}/report?token={token}"
        ),
    )


@router.get("/{object_id}/report")
async def report(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[ExportQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    from billing_platform.bulk_files import csv_document

    current.actor.require_scope("accounting.export.read", target=ScopePath(company_id=company_id))
    if (await report_codec(db, current, object_id, request)).decode(query.token) != {
        "id": str(object_id)
    }:
        raise ValidationFailedError("invalid import report ticket")
    row = await company_object(db, FinancialOpeningImport, object_id, company_id=company_id)
    result = await tasks.detail(db, current, object_id)
    rows = [
        [
            str(row.id),
            row.state,
            str(result.drafts_complete).lower(),
            str(row.batch_id or ""),
            str(journal),
            "",
        ]
        for journal in result.journal_ids
    ]
    rows += [
        [
            str(row.id),
            row.state,
            str(result.drafts_complete).lower(),
            str(row.batch_id or ""),
            "",
            str(issue.get("message", "Review this import")),
        ]
        for issue in result.issues
    ]
    if not rows:
        rows = [[str(row.id), row.state, "false", "", "", "No native drafts created"]]
    audit(db, current, row, "export")
    return Response(
        csv_document(
            ["job_id", "status", "drafts_complete", "opening_batch_id", "journal_id", "message"],
            rows,
        ),
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="financial-opening-import.csv"',
        },
    )
