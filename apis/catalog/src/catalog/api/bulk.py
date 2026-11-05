"""Protected bulk job routes; long validation and commit run in a separate worker."""

import uuid
from typing import Annotated, Any

from billing_platform.authz import ScopePath
from billing_platform.bulk_files import csv_document, xlsx_document
from billing_platform.errors import ConflictError, ErrorEnvelope, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.bulk_limits import BoundedBulkRoute
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.events.evidence import report_access
from catalog.schemas.bulk import (
    BulkQuery,
    CommitJob,
    JobAction,
    JobDetail,
    JobListItem,
    RecordListItem,
    RecordPreview,
    ReportDownload,
    ReportOptions,
    ReportTicket,
    ReviseJob,
    StageInput,
    Template,
    TemplateQuery,
    ValidateJob,
)
from catalog.tasks import bulk_jobs
from catalog.tasks.bulk_access import require_bulk, scoped_job
from catalog.tasks.bulk_inputs import CONTROLS
from catalog.tasks.bulk_registry import operation
from catalog.tasks.bulk_reports import report_codec
from catalog.tasks.field_context import FieldContext, load_field_context


async def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


router = APIRouter(
    route_class=BoundedBulkRoute,
    dependencies=[Depends(private_response)],
    prefix="/v1/companies/{company_id}/bulk-jobs",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 413, 422, 429, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    body: Any,
    key: str,
    action: str,
    job_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    bucket = "bulk:" + current.tenant_id.hex + company.hex + current.user_id.hex
    if not request.app.state.pricing_limiter.allow(bucket, limit=20):
        raise HTTPException(status_code=429, detail="bulk write rate exceeded")
    result = await bulk_jobs.command(
        request.app.state.session_factory, current, company, body, key, action=action, job_id=job_id
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={
            "Idempotency-Replayed": str(result.replayed).lower(),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/templates",
    response_model=Template,
    operation_id="get_catalog_bulk_template",
    responses={
        200: {
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
            }
        }
    },
    dependencies=[Depends(unique_query)],
)
async def template(
    company_id: uuid.UUID,
    query: Annotated[TemplateQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    await require_bulk(db, current, company_id, "catalog.bulk.manage")
    op = operation(query.resource, query.action)
    for permission in op.permissions:
        current.require_scope(permission, target=ScopePath(company_id=company_id))
    context = await load_field_context(db, current, company_id, "catalog." + query.resource)
    if not set(context.native.fields) <= context.readable():
        raise PermissionDeniedError("template requires readable resource fields")
    document = op.schema.model_json_schema()
    document["x-catalog-custom-fields"] = [
        field.model_dump(mode="json")
        for field in context.definitions
        if "custom_field:" + field.key in context.readable()
    ]
    document["x-catalog-automatic-fields"] = [
        field
        for field in ("expected_version", "expected_generation", "expected_source_version")
        if field in op.schema.model_fields
    ]
    result = Template(
        resource=query.resource,
        actions=[query.action],
        schema_document=document,
        required_permissions=sorted(op.permissions),
    )
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if query.format == "JSON":
        return JSONResponse(result.model_dump(mode="json"), headers=headers)
    columns = [
        *CONTROLS,
        *[
            name
            for name in op.schema.model_fields
            if name not in document["x-catalog-automatic-fields"]
        ],
    ]
    content = (
        csv_document(columns, [], template=True)
        if query.format == "CSV"
        else xlsx_document(columns, [])
    )
    headers["Content-Disposition"] = "attachment; filename=catalog-template." + query.format.lower()
    return Response(
        content,
        media_type="text/csv"
        if query.format == "CSV"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("", status_code=202, response_model=JobDetail, operation_id="stage_catalog_bulk_job")
async def stage(
    company_id: uuid.UUID,
    body: StageInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "stage")


@router.get(
    "",
    response_model=Page[JobListItem],
    operation_id="list_catalog_bulk_jobs",
    dependencies=[Depends(unique_query)],
)
async def jobs(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[BulkQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[Any]:
    return await bulk_jobs.list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get("/{job_id}", response_model=JobDetail, operation_id="get_catalog_bulk_job")
async def get_job(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> JobDetail:
    no_query(request)
    return await bulk_jobs.detail(db, current, company_id, job_id)


@router.get(
    "/{job_id}/records",
    response_model=Page[RecordListItem],
    operation_id="list_catalog_bulk_records",
    dependencies=[Depends(unique_query)],
)
async def records(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    query: Annotated[BulkQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[Any]:
    return await bulk_jobs.list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        job_id=job_id,
    )


@router.get(
    "/{job_id}/records/{record_id}",
    response_model=RecordPreview,
    operation_id="get_catalog_bulk_preview",
)
async def preview(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> RecordPreview:
    no_query(request)
    return await bulk_jobs.preview(db, current, company_id, job_id, record_id)


@router.post(
    "/{job_id}/validate",
    status_code=202,
    response_model=JobDetail,
    operation_id="validate_catalog_bulk_job",
)
async def validate(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ValidateJob,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "validate", job_id)


@router.post(
    "/{job_id}/commit",
    status_code=202,
    response_model=JobDetail,
    operation_id="commit_catalog_bulk_job",
)
async def commit(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: CommitJob,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "commit", job_id)


@router.post(
    "/{job_id}/cancel",
    status_code=202,
    response_model=JobDetail,
    operation_id="cancel_catalog_bulk_job",
)
async def cancel(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: JobAction,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "cancel", job_id)


@router.post(
    "/{job_id}/revise",
    status_code=202,
    response_model=JobDetail,
    operation_id="revise_catalog_bulk_job",
)
async def revise(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ReviseJob,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, "revise", job_id)


@router.get(
    "/{job_id}/report",
    operation_id="download_catalog_bulk_report",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
            }
        }
    },
    dependencies=[Depends(unique_query)],
)
async def report(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    query: Annotated[ReportDownload, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    job = await scoped_job(db, current, company_id, job_id, live=True)
    decoded = report_codec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(), current, job
    ).decode(query.token)
    if decoded != {"version": job.row_version, "format": query.format}:
        raise ConflictError("report changed; request a fresh download ticket")
    rows = await bulk_jobs.records(db, job)
    data = []
    contexts: dict[str, FieldContext] = {}
    for row in rows:
        reviewed = await bulk_jobs.render_preview(db, current, company_id, row, contexts=contexts)
        data.append(
            [
                row.source_sheet,
                str(row.source_row),
                row.logical_key,
                row.state,
                row.error_code or "",
                ",".join(reviewed.error_fields),
            ]
        )
    columns = ["sheet", "row", "key", "state", "error_code", "columns"]
    content = csv_document(columns, data) if query.format == "CSV" else xlsx_document(columns, data)
    report_access(db, current, company_id, job_id, count=len(data), file_format=query.format)
    await db.commit()  # Persist access evidence before sending a successful file response.
    return Response(
        content,
        media_type="text/csv"
        if query.format == "CSV"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=catalog-results." + query.format.lower(),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{job_id}/report-ticket",
    response_model=ReportTicket,
    operation_id="get_catalog_bulk_report_ticket",
    dependencies=[Depends(unique_query)],
)
async def report_ticket(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    query: Annotated[ReportOptions, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ReportTicket:
    job = await scoped_job(db, current, company_id, job_id, live=True)
    token = report_codec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(), current, job
    ).encode({"version": job.row_version, "format": query.format})
    return ReportTicket(
        download_path=f"/v1/companies/{company_id}/bulk-jobs/{job_id}/report?format={query.format}&token={token}"
    )
