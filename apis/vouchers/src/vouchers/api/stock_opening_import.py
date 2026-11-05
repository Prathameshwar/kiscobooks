"""Opening import staging, bounded dry-run/commit, history and protected results."""

import uuid
from typing import Annotated, Any

from billing_platform.bulk_files import csv_document
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.api.imports import limited
from vouchers.domain.stock_opening_import import MARKER, OPTIONAL, REQUIRED
from vouchers.models.stock_opening_import import StockOpeningImport
from vouchers.schemas.configuration import Contract
from vouchers.schemas.stock_opening_import import (
    OpeningImportCommit,
    OpeningImportDetail,
    OpeningImportStage,
    OpeningImportVersion,
)
from vouchers.tasks import stock_opening_import as tasks
from vouchers.tasks.access import fingerprint
from vouchers.tasks.common import audit, get

router = APIRouter(
    prefix="/v1/companies/{company_id}/stock-opening-imports",
    responses=ERRORS,
    dependencies=[Depends(unique_query)],
)


class ImportListItem(Contract):
    id: uuid.UUID
    row_version: int
    source_key: str
    state: str


def codec(request: Request, current: Access, subject: str, *, ttl: int = 300) -> CursorCodec:
    return CursorCodec(
        request.app.state.settings.artifact_signing_secret.get_secret_value().encode(),
        context=canonical_json(
            {
                "resource": "stock-opening-imports",
                "tenant": str(current.actor.tenant_id),
                "company": str(current.context.company_id),
                "authority": fingerprint(current),
                "subject": subject,
            }
        ).decode(),
        ttl_seconds=ttl,
    )


@router.get("/template")
async def template(company_id: uuid.UUID, current: Access = Depends(access)) -> dict[str, Any]:
    tasks.require(current, "import.manage")
    return {
        "marker": MARKER,
        "version": 1,
        "required_columns": REQUIRED,
        "optional_columns": OPTIONAL,
        "formats": ["JSON", "CSV", "TSV", "XLSX"],
        "reference_policy": "Use exact authorized owner IDs; names/codes are rejected.",
        "effect": "Creates native drafts. Approve, post and finalize cutover separately.",
    }


@router.get("", response_model=Page[ImportListItem])
async def listing(
    company_id: uuid.UUID,
    query: Annotated[ListQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[ImportListItem]:
    tasks.require(current, "import.read")
    if query.q:
        raise ValidationFailedError(
            "opening import history supports ID ordering, not free-text search"
        )
    terms = resolve_sort(
        query.sort,
        default="-id",
        columns={"id": SortColumn(StockOpeningImport.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        select(
            StockOpeningImport.id,
            StockOpeningImport.row_version,
            StockOpeningImport.source_key,
            StockOpeningImport.state,
        ).where(StockOpeningImport.company_id == company_id),
        query=query,
        terms=terms,
        codec=codec(
            request,
            current,
            "history:" + canonical_json(query.model_dump(mode="json", exclude={"cursor"})).decode(),
        ),
        project=lambda row: ImportListItem.model_validate(dict(row)),
    )


@router.post("", response_model=OpeningImportDetail, status_code=201)
async def stage(
    company_id: uuid.UUID,
    body: OpeningImportStage,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    limited(request, current, scope="sopen-stage", limit=10)
    with tenant_scope(current.actor.tenant_id):
        return response(
            await tasks.stage(request.app.state.session_factory, current, body, idempotency_key)
        )


@router.get("/{job_id}", response_model=OpeningImportDetail)
async def detail(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.detail(db, current, await get(db, current, StockOpeningImport, job_id))


@router.post("/{job_id}/validate", response_model=OpeningImportDetail)
async def validate(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: OpeningImportVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    limited(request, current, scope="sopen-step", limit=120)
    with tenant_scope(current.actor.tenant_id):
        return response(
            await tasks.advance(
                request.app.state.session_factory,
                current,
                job_id,
                "validate",
                body,
                idempotency_key,
            )
        )


@router.post("/{job_id}/commit", response_model=OpeningImportDetail)
async def commit(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: OpeningImportCommit,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    limited(request, current, scope="sopen-step", limit=120)
    with tenant_scope(current.actor.tenant_id):
        return response(
            await tasks.advance(
                request.app.state.session_factory, current, job_id, "commit", body, idempotency_key
            )
        )


@router.post("/{job_id}/cancel", response_model=OpeningImportDetail)
async def cancel(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: OpeningImportVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    with tenant_scope(current.actor.tenant_id):
        return response(
            await tasks.advance(
                request.app.state.session_factory, current, job_id, "cancel", body, idempotency_key
            )
        )


@router.get("/{job_id}/report-ticket")
async def ticket(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    row = await get(db, current, StockOpeningImport, job_id)
    await tasks.detail(db, current, row)
    token = codec(request, current, f"report:{row.id}:{row.row_version}").encode(
        {"id": str(job_id)}
    )
    return {
        "token": token,
        "expires_in": 300,
        "download_path": (
            f"/v1/companies/{company_id}/stock-opening-imports/{job_id}/report?token={token}"
        ),
    }


@router.get("/{job_id}/report", response_class=Response)
async def report(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    token: Annotated[str, Query(max_length=4096)],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    row = await get(db, current, StockOpeningImport, job_id)
    value = await tasks.detail(db, current, row)
    if codec(request, current, f"report:{row.id}:{row.row_version}").decode(token) != {
        "id": str(job_id)
    }:
        raise ValidationFailedError("invalid opening import report ticket")
    records = [
        [str(item["chunk"]), item["voucher_id"], item["voucher_status"], "", ""]
        for item in value["effects"]
    ]
    records.extend(
        [
            [str(item["chunk"]), "", "BLOCKED", item["code"], item["message"]]
            for item in value["errors"]
        ]
    )
    audit(db, current, "stock_opening_import", row.id, "report_access")
    return Response(
        csv_document(
            ["chunk", "voucher_id", "state", "code", "message"],
            records,
            marker="_stock_opening_result_version",
        ),
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="opening-import-results.csv"',
        },
    )
