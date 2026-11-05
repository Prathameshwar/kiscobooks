"""Additive voucher import history, correction and private download contracts."""

import uuid
from typing import Annotated, Any, Literal

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.import_contracts import DownloadTicket
from billing_platform.import_routes import FILE_CONTENT, file_response
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.api.imports import limited, secret, validate
from vouchers.schemas.imports import (
    AttemptResultPage,
    HistoryPage,
    HistoryQuery,
    ImportDownload,
    ImportDownloadRequest,
    ImportJobDetail,
    ImportRevisionInput,
    ImportVersion,
    TemplateSnapshotDetail,
    TemplateSnapshotInput,
)
from vouchers.tasks import import_extensions as tasks
from vouchers.tasks import imports as run

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    tags=["voucher-imports"],
    responses=ERRORS,
    dependencies=[Depends(unique_query)],
)


@router.post(
    "/voucher-import-template-snapshots",
    response_model=TemplateSnapshotDetail,
    status_code=201,
    operation_id="create_voucher_import_template_snapshot",
)
async def template(
    company_id: uuid.UUID,
    body: TemplateSnapshotInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> Response:
    limited(request, current)
    return response(
        await tasks.create_template(
            request.app.state.session_factory, current, idempotency_key, body
        )
    )


@router.get(
    "/voucher-import-template-snapshots/{template_id}",
    response_model=TemplateSnapshotDetail,
    operation_id="get_voucher_import_template_snapshot",
)
async def template_snapshot(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return tasks.template_view(await tasks.checked_template(db, current, template_id))


@router.post(
    "/voucher-imports/{job_id}/revisions",
    response_model=ImportJobDetail,
    operation_id="revise_voucher_import",
)
async def revision(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportRevisionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> Response:
    limited(request, current)
    return response(
        await tasks.revise(
            request.app.state.session_factory, current, idempotency_key, job_id, body
        )
    )


@router.post(
    "/voucher-imports/{job_id}/retry",
    response_model=ImportJobDetail,
    operation_id="retry_voucher_import",
)
async def retry(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> Response:
    return await validate(company_id, job_id, body, request, idempotency_key, current)


@router.get(
    "/voucher-imports/{job_id}/history/{kind}",
    response_model=HistoryPage,
    operation_id="list_voucher_import_history",
)
async def history(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    kind: Literal["attempts", "revisions"],
    query: Annotated[HistoryQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.history(
        db, current, secret(request), job_id, kind, query.limit, query.cursor
    )


@router.get(
    "/voucher-imports/{job_id}/attempts/{attempt_id}/results",
    response_model=AttemptResultPage,
    operation_id="list_voucher_import_attempt_results",
)
async def results(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    query: Annotated[HistoryQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.attempt_results(
        db, current, secret(request), job_id, attempt_id, query.limit, query.cursor
    )


@router.post(
    "/voucher-imports/{job_id}/download-ticket",
    response_model=DownloadTicket,
    operation_id="create_voucher_import_download_ticket",
)
async def ticket(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportDownload,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    run.require(current, "import.read")
    job = await run.scoped_job(db, current, job_id)
    return {
        "token": run.report_codec(secret(request), current, job).encode(
            {"version": job.row_version, "options": body.model_dump(mode="json")}
        ),
        "expires_in": 300,
    }


@router.post(
    "/voucher-imports/{job_id}/download",
    response_class=Response,
    responses={
        200: {
            "content": FILE_CONTENT
            | {"application/json": {"schema": {"type": "string", "format": "binary"}}}
        }
    },
    operation_id="download_voucher_import_data",
)
async def download(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportDownloadRequest,
    request: Request,
    current: Access = Depends(access),
) -> Response:
    run.require(current, "import.read")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory.begin() as db:
            job = await run.scoped_job(db, current, job_id)
            options = ImportDownload.model_validate(body.model_dump(exclude={"token"}))
            if run.report_codec(secret(request), current, job).decode(body.token) != {
                "version": job.row_version,
                "options": options.model_dump(mode="json"),
            }:
                raise ConflictError("import changed; request a fresh download ticket")
            content, filename = await tasks.download(db, current, job_id, options)
    result = file_response(content, filename)
    if filename.endswith(".json"):
        result.headers["Content-Type"] = "application/json"
    return result
