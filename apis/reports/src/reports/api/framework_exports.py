"""Independent exports and private streaming downloads with fresh actor/scope checks."""

import asyncio
import uuid
from dataclasses import asdict
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.display import DisplayConfiguration
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from fastapi import Depends, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.api.framework_runs import authorize_job, command, detail
from reports.api.routes import Idempotency, codec
from reports.domain.reporting.contracts import fingerprint as hash_value
from reports.domain.reporting.views import select as select_view
from reports.models.export_artifacts import ReportExportArtifact
from reports.models.framework import ReportJob
from reports.schemas.framework import ArtifactDownload, ExportRequest, JobDetail
from reports.storage.filesystem import chunks
from reports.tasks import export_artifacts as artifacts
from reports.tasks import framework_jobs as jobs
from reports.tasks.access import authorize, fingerprint
from reports.tasks.capacity import CapacityExceededError
from reports.tasks.common import audit, get


@router.post("/report-runs/{identity}/exports", response_model=JobDetail, status_code=202)
async def create_export(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    body: ExportRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    authorize(current, "report.export")
    settings = request.app.state.settings
    if not settings.exports_enabled or settings.artifact_root is None:
        raise ConflictError("report export admission is not enabled or storage is unavailable")
    renderer = artifacts.definition(body.format, settings)
    if body.delivery == "PACKAGE" and body.format not in {"PDF", "HTML"}:
        raise ValidationFailedError("package delivery requires PDF or HTML")
    if body.part_rows is not None and body.delivery != "PACKAGE":
        raise ValidationFailedError("part size requires package delivery")

    async def check(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        parent = await get(db, company_id, ReportJob, identity)
        authorize_job(current, parent)
        if parent.kind != "RUN" or parent.status != "COMPLETE":
            raise ConflictError("export requires a completed result")
        balance_standard = (
            parent.definition["code"] == "BALANCE_SHEET"
            and parent.definition["version"] >= 6
            and body.view == "default"
            and body.format in {"PDF", "HTML"}
        )
        if balance_standard and body.delivery == "PACKAGE":
            raise ValidationFailedError(
                "Standard Balance Sheet print requires a single complete document; "
                "use CSV/Excel for larger statements or Comparative for package delivery"
            )
        if body.trial_balance is not None:
            from reports.queries.trial_presentation import validate

            if parent.definition["code"] != "TRIAL_BALANCE" or parent.definition["version"] != 6:
                raise ValidationFailedError(
                    "hierarchy export choices require the current Trial Balance"
                )
            await validate(db, parent, body.trial_balance)
        if parent.definition["code"] in {"GSTR3B", "GSTR1"} and (
            body.format not in {"PDF", "XLSX", "CSV"} or body.delivery != "SINGLE"
        ):
            raise ValidationFailedError(
                "GST returns support a complete preparation PDF, Excel workbook or detail CSV"
            )
        if body.view not in {view["key"] for view in parent.definition["views"]}:
            raise ValidationFailedError("retained export view is unavailable")
        selected = select_view(parent.definition["views"], body.view)
        cell_columns = len(selected["columns"])
        if (
            parent.definition["code"] == "TRIAL_BALANCE"
            and parent.definition["version"] == 6
            and body.format in {"CSV", "XLSX"}
        ):
            cell_columns += 4
        calculated = select_view(
            parent.definition["views"], (parent.options or {}).get("view", "default")
        )
        if selected.get("calculation", "detail") != calculated.get("calculation", "detail"):
            raise ValidationFailedError("export view requires a new report calculation")
        if body.format in {"HTML", "PDF"}:
            try:
                DisplayConfiguration.model_validate(parent.display)
            except ValidationError as exc:
                raise ConflictError(
                    "retained report display is unavailable for this renderer"
                ) from exc
        limit = settings.export_max_rows if body.delivery == "PACKAGE" else renderer.max_rows
        if parent.completed_rows > limit:
            if balance_standard:
                raise CapacityExceededError(
                    "Standard Balance Sheet exceeds the complete-document limit; "
                    "use CSV/Excel or Comparative package delivery"
                )
            raise CapacityExceededError(
                "completed result exceeds this delivery; "
                "select PACKAGE, CSV/XLSX or a narrower period"
            )
        if body.delivery == "SINGLE" and parent.completed_rows * cell_columns > renderer.max_cells:
            raise CapacityExceededError("completed result exceeds the selected export cell limit")
        if body.delivery == "PACKAGE":
            part_rows = min(
                body.part_rows or (1000 if body.format == "PDF" else 10000),
                renderer.max_rows,
                renderer.max_cells // cell_columns,
            )
            if (
                part_rows < 1
                or (parent.completed_rows + part_rows - 1) // part_rows > settings.package_max_parts
            ):
                raise CapacityExceededError("completed result exceeds the package part limit")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await jobs.admit(db)
        parent = await get(db, company_id, ReportJob, identity)
        parameters = body.model_dump(exclude_none=True) | {
            "renderer": asdict(renderer),
            **(
                {
                    "package": {
                        "max_parts": settings.package_max_parts,
                        "max_rows": settings.export_max_rows,
                        "max_bytes": settings.export_max_bytes,
                        "timeout_seconds": settings.export_timeout_seconds,
                    }
                }
                if body.delivery == "PACKAGE"
                else {}
            ),
        }
        row = ReportJob(
            tenant_id=current.actor.tenant_id,
            company_id=company_id,
            actor_id=current.actor.user_id,
            generation_id=parent.generation_id,
            parent_id=identity,
            kind="EXPORT",
            lane="RENDER" if body.format == "PDF" and body.delivery == "SINGLE" else "BULK",
            definition=parent.definition,
            parameters=parameters,
            display=parent.display,
            options={"view": body.view},
            permission_hash=fingerprint(current),
            request_hash=hash_value(
                {"run": str(identity), "export": parameters, "permission": fingerprint(current)}
            ),
            created_by=current.actor.user_id,
        )
        db.add(row)
        await db.flush()
        jobs.dispatch(db, row)
        audit(db, row.tenant_id, company_id, row.id, "requested", row.actor_id)
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> JobDetail:
        row = await get(db, company_id, ReportJob, uuid.UUID(refs["id"]))
        authorize_job(current, row)
        return detail(row)

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            current.actor.tenant_id,
            company_id,
            current.actor.user_id,
            "reports.v2.export.create",
            idempotency_key,
            {"run": str(identity), **body.model_dump(mode="json")},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
    return JSONResponse(result.value.model_dump(mode="json"), status_code=result.status)


async def export_job(
    db: AsyncSession, company: uuid.UUID, identity: uuid.UUID, current: Access
) -> ReportJob:
    row = await get(db, company, ReportJob, identity)
    authorize_job(current, row)
    if row.kind != "EXPORT":
        raise ConflictError("export job required")
    return row


@router.get("/report-exports/{identity}", response_model=JobDetail)
async def status(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
) -> JobDetail:
    authorize(current, "report.export")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            return detail(await export_job(db, company_id, identity, current))


@router.post("/report-exports/{identity}/cancel", response_model=JobDetail)
async def cancel(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    authorize(current, "report.export")
    return await command(
        company_id, identity, request, current, idempotency_key, "cancel", "EXPORT"
    )


@router.post("/report-exports/{identity}/retry", response_model=JobDetail)
async def retry(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    authorize(current, "report.export")
    return await command(company_id, identity, request, current, idempotency_key, "retry", "EXPORT")


async def published(
    db: AsyncSession, company: uuid.UUID, identity: uuid.UUID, current: Access
) -> ReportExportArtifact:
    job = await export_job(db, company, identity, current)
    row = await db.scalar(
        select(ReportExportArtifact).where(
            ReportExportArtifact.company_id == company,
            ReportExportArtifact.job_id == job.id,
            ReportExportArtifact.attempt == job.attempt,
            ReportExportArtifact.state == "PUBLISHED",
        )
    )
    if job.status != "COMPLETE" or row is None:
        raise ConflictError("completed export artifact required")
    return row


@router.get("/report-exports/{identity}/download-token", response_model=ArtifactDownload)
async def token(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    response: Response,
    current: Annotated[Access, Depends(access)],
) -> ArtifactDownload:
    authorize(current, "report.export")
    response.headers["Cache-Control"] = "no-store"
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            row = await published(db, company_id, identity, current)
            assert row.content_hash is not None and row.byte_count is not None
            return ArtifactDownload(
                token=codec(request, current, f"v2.download:{identity}", 120).encode(
                    {"artifact": str(row.id), "hash": row.content_hash}
                ),
                content_hash=row.content_hash,
                byte_count=row.byte_count,
                filename=row.filename,
            )


@router.get("/report-exports/{identity}/download")
async def download(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
    token: Annotated[str, Query(max_length=4096)],
) -> StreamingResponse:
    authorize(current, "report.export")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            row = await published(db, company_id, identity, current)
            permitted = codec(request, current, f"v2.download:{identity}", 120).decode(token)
            if permitted != {"artifact": str(row.id), "hash": row.content_hash}:
                raise PermissionDeniedError("download token does not match the completed artifact")
            audit(db, row.tenant_id, company_id, row.id, "exported", current.actor.user_id)
    assert row.byte_count is not None
    try:
        storage = await asyncio.to_thread(artifacts.store, request.app.state.settings)
        stream = await asyncio.to_thread(storage.open, row.storage_key, row.byte_count)
    except (OSError, ValueError) as exc:
        raise ConflictError("retained artifact storage is unavailable") from exc
    return StreamingResponse(
        chunks(stream),
        media_type=row.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{row.filename}"',
            "Content-Length": str(row.byte_count),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )
