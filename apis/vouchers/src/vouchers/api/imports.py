"""Purchase import routes: template, stage, validate, commit, results and report download."""

import asyncio
import re
import uuid
from typing import Annotated, Any

from billing_platform.bulk_files import csv_document, xlsx_workbook
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult
from billing_platform.import_routes import FILE_CONTENT
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.domain import import_kinds as kinds
from vouchers.domain import imports as rules
from vouchers.schemas.imports import (
    ImportCommit,
    ImportJobDetail,
    ImportJobPage,
    ImportQuery,
    ImportRowQuery,
    ImportStage,
    ImportVersion,
    ImportVoucherDetail,
    ImportVoucherPage,
    ReportDownload,
    ReportQuery,
    ReportTicket,
    TemplateQuery,
)
from vouchers.tasks import imports as tasks
from vouchers.tasks.common import audit

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses=ERRORS,
    dependencies=[Depends(unique_query)],
    tags=["voucher-imports"],
)


def limited(request: Request, current: Access, *, scope: str = "import", limit: int = 30) -> None:
    # Bulk uploads and commits are bounded separately from ordinary writes (§5.13). Steps of a
    # running job have their own allowance so one 500-voucher job can finish in a minute.
    key = f"{scope}:{current.actor.tenant_id}:{current.context.company_id}:{current.actor.user_id}"
    if not request.app.state.write_limiter.allow(key, limit=limit):
        raise HTTPException(status_code=429, detail="import rate limit exceeded")


def secret(request: Request) -> bytes:
    value: bytes = request.app.state.settings.artifact_signing_secret.get_secret_value().encode()
    return value


async def advance(request: Request, current: Access, job_id: uuid.UUID) -> None:
    """Run one bounded validation or commit step for the job's current state."""
    factory = request.app.state.session_factory
    tasks.require(current, "import.read")
    with tenant_scope(current.actor.tenant_id):
        async with factory() as db:
            job = await tasks.scoped_job(db, current, job_id)
            tasks.actionable(job)
            state = job.state
    if state == "VALIDATING":
        settings = request.app.state.settings
        await tasks.validate_step(
            factory,
            current,
            job_id,
            lookup_owner=settings.master_lookup_owner,
            execution_owner=settings.execution_owner,
            resolve=tasks.default_lookup,
            preview=tasks.preview_owner,
        )
    elif state == "COMMITTING":
        await tasks.commit_step(factory, current, job_id)


async def current_job(request: Request, current: Access, job_id: uuid.UUID) -> dict[str, Any]:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            return await tasks.job_detail(db, current, job_id)


@router.get(
    "/voucher-import-templates",
    operation_id="download_voucher_import_template",
    response_class=Response,
    responses={200: {"content": FILE_CONTENT | {"application/json": {}}}},
)
async def template(
    company_id: uuid.UUID,
    query: Annotated[TemplateQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    tasks.require(current, "import.manage", "create")
    kind, revision = await tasks.import_type(db, current, query.voucher_type_id)
    shape, _ = await tasks.shape_for(
        db,
        current,
        revision,
        kind.kind,
        document_date=query.document_date,
        posting_date=query.posting_date,
        class_id=query.class_id,
    )
    code = re.sub(r"[^A-Za-z0-9_-]", "_", kind.code)
    raw, media, name = await asyncio.to_thread(
        tasks.template_document, shape, query.format, code, kind.kind
    )
    return Response(
        raw,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/voucher-imports",
    status_code=202,
    response_model=ImportJobDetail,
    operation_id="stage_voucher_import",
)
async def stage(
    company_id: uuid.UUID,
    body: ImportStage,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    limited(request, current)

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await tasks.job_detail(db, current, uuid.UUID(refs["id"]))

    return response(
        await tasks.stage(
            request.app.state.session_factory,
            current,
            idempotency_key,
            type_id=body.voucher_type_id,
            file_format=body.format,
            content=body.content_base64,
            document=body.document,
            duplicate_rule=body.duplicate_rule,
            template_id=body.template_id,
            render=render,
        )
    )


@router.get("/voucher-imports", response_model=ImportJobPage, operation_id="list_voucher_imports")
async def jobs(
    company_id: uuid.UUID,
    query: Annotated[ImportQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.job_page(
        db,
        current,
        secret(request),
        limit=query.limit,
        cursor=query.cursor,
        state=query.state,
        mine=query.mine,
    )


@router.get(
    "/voucher-imports/{job_id}", response_model=ImportJobDetail, operation_id="get_voucher_import"
)
async def job(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.job_detail(db, current, job_id)


@router.get(
    "/voucher-imports/{job_id}/vouchers",
    response_model=ImportVoucherPage,
    operation_id="list_voucher_import_vouchers",
)
async def vouchers(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    query: Annotated[ImportRowQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.row_page(
        db,
        current,
        secret(request),
        job_id,
        limit=query.limit,
        cursor=query.cursor,
        state=query.state,
    )


@router.get(
    "/voucher-imports/{job_id}/vouchers/{import_key}",
    response_model=ImportVoucherDetail,
    response_model_exclude_none=True,
    operation_id="get_voucher_import_voucher",
)
async def voucher(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    import_key: str,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await tasks.row_detail(db, current, job_id, import_key)


async def transition(
    request: Request,
    current: Access,
    key: str,
    job_id: uuid.UUID,
    action: str,
    body: dict[str, Any],
) -> JSONResponse:
    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await tasks.job_detail(db, current, uuid.UUID(refs["id"]))

    result = await tasks.transition(
        request.app.state.session_factory, current, key, job_id, action, body, render
    )
    if action != "cancel" and not result.replayed:
        await advance(request, current, job_id)
        result = CommandResult(
            result.status, await current_job(request, current, job_id), result.replayed
        )
    return response(result)


@router.post(
    "/voucher-imports/{job_id}/validate",
    response_model=ImportJobDetail,
    operation_id="validate_voucher_import",
)
async def validate(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    limited(request, current)
    settings = request.app.state.settings
    # Fail before the state change when validation could not run at all.
    tenant, company = current.actor.tenant_id, current.context.company_id
    tasks.require(current, "import.manage", "create")
    tasks.owner_for(settings.master_lookup_owner, tenant, company)
    with tenant_scope(tenant):
        async with request.app.state.session_factory() as db:
            kind = (await tasks.scoped_job(db, current, job_id)).kind
    if kinds.family(kind) == "INVOICE":
        tasks.owner_for(settings.execution_owner, tenant, company, "invoice calculation")
    return await transition(
        request, current, idempotency_key, job_id, "validate", body.model_dump(mode="json")
    )


@router.post(
    "/voucher-imports/{job_id}/commit",
    response_model=ImportJobDetail,
    operation_id="commit_voucher_import",
)
async def commit(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportCommit,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    limited(request, current)
    return await transition(
        request, current, idempotency_key, job_id, "commit", body.model_dump(mode="json")
    )


@router.post(
    "/voucher-imports/{job_id}/cancel",
    response_model=ImportJobDetail,
    operation_id="cancel_voucher_import",
)
async def cancel(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ImportVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await transition(
        request, current, idempotency_key, job_id, "cancel", body.model_dump(mode="json")
    )


@router.post(
    "/voucher-imports/{job_id}/run",
    response_model=ImportJobDetail,
    operation_id="run_voucher_import",
)
async def run(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
) -> dict[str, Any]:
    """Advance a validating or committing job by one bounded step.

    Naturally idempotent: rows move forward once and every draft has its own
    per-voucher idempotency key and unique effect, so a repeat creates nothing.
    """
    limited(request, current, scope="import-step", limit=120)
    await advance(request, current, job_id)
    return await current_job(request, current, job_id)


@router.get(
    "/voucher-imports/{job_id}/report-ticket",
    response_model=ReportTicket,
    operation_id="get_voucher_import_report_ticket",
)
async def report_ticket(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    query: Annotated[ReportQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    tasks.require(current, "import.read")
    job = await tasks.scoped_job(db, current, job_id)
    token = tasks.report_codec(secret(request), current, job).encode(
        {"version": job.row_version, "format": query.format}
    )
    return {
        "download_path": f"/v1/companies/{company_id}/voucher-imports/{job_id}/report"
        f"?format={query.format}&token={token}",
        "expires_in": tasks.REPORT_TTL,
    }


@router.get(
    "/voucher-imports/{job_id}/report",
    operation_id="download_voucher_import_report",
    response_class=Response,
    responses={200: {"content": FILE_CONTENT}},
)
async def report(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    query: Annotated[ReportDownload, Query()],
    request: Request,
    current: Access = Depends(access),
) -> Response:
    tasks.require(current, "import.read")
    with tenant_scope(current.actor.tenant_id):
        # The access audit commits before any byte of the report is sent.
        async with request.app.state.session_factory() as db, db.begin():
            job = await tasks.scoped_job(db, current, job_id)
            try:
                ticket = tasks.report_codec(secret(request), current, job).decode(query.token)
            except ValidationFailedError as error:
                raise ValidationFailedError(
                    "report link is invalid or expired; request a new one"
                ) from error
            if ticket != {"version": job.row_version, "format": query.format}:
                raise ConflictError("report changed; request a fresh download link")
            rows = await tasks.report_rows(db, current, job)
            audit(db, current, "import_job", job.id, "report_access", changes={"rows": len(rows)})
    if query.format == "XLSX":
        raw = await asyncio.to_thread(
            xlsx_workbook, [("results", tasks.REPORT_COLUMNS, rows)], marker=rules.MARKER
        )
        media = tasks.FILE_MEDIA["XLSX"]
    else:
        raw = await asyncio.to_thread(
            csv_document,
            tasks.REPORT_COLUMNS,
            rows,
            delimiter="\t" if query.format == "TSV" else ",",
        )
        media = tasks.FILE_MEDIA[query.format]
    name = f"voucher-import-{job_id}.{query.format.lower()}"
    return Response(
        raw, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )
