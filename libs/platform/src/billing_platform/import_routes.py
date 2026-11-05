"""Optional FastAPI boundary; business adapters are provided by each owner API."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    ErrorEnvelope,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.import_contracts import (
    CommitImport,
    DownloadOptions,
    DownloadRequest,
    DownloadTicket,
    ImportAction,
    ImportArtifactItem,
    ImportAttemptItem,
    ImportDefinitions,
    ImportDetail,
    ImportIssueItem,
    ImportJobListItem,
    ImportRecordItem,
    ImportRevisionItem,
    ReviseImport,
    StageImport,
    TemplateDetail,
    TemplateRequest,
)
from billing_platform.import_engine import (
    ImportAdapter,
    ImportPreflight,
    authorize_snapshot,
    command,
    detail,
    scoped_job,
)
from billing_platform.import_files import template_document
from billing_platform.import_http import BoundedImportRoute, required_key, strict_query
from billing_platform.import_models import ImportTemplateSnapshot
from billing_platform.import_reads import codec, download, history, record_history
from billing_platform.listing import Page

FILE_CONTENT = {
    media: {"schema": {"type": "string", "format": "binary"}}
    for media in (
        "text/csv",
        "text/tab-separated-values",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
}


def router_for(
    namespace: str,
    dependency: Callable[..., Any],
    build: Callable[[Request, Any, uuid.UUID], ImportAdapter | Awaitable[ImportAdapter]],
) -> APIRouter:
    current_dependency = Depends(dependency)

    async def adapter_for(request: Request, current: Any, company: uuid.UUID) -> ImportAdapter:
        value = build(request, current, company)
        if inspect.isawaitable(value):
            return await value
        return value

    router = APIRouter(
        route_class=BoundedImportRoute,
        dependencies=[Depends(strict_query)],
        prefix="/v1/companies/{company_id}",
        tags=["Imports"],
        responses={
            code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 413, 422, 429, 503)
        },
    )

    def secret(request: Request) -> bytes:
        return cast(
            bytes, request.app.state.settings.actor_signing_secret.get_secret_value().encode()
        )

    def private(value: Any, *, status: int = 200) -> JSONResponse:
        return JSONResponse(
            value,
            status_code=status,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    async def write(
        request: Request,
        current: Any,
        company: uuid.UUID,
        body: Any,
        action: str,
        job_id: uuid.UUID | None = None,
    ) -> JSONResponse:
        if request.query_params:
            raise ValidationFailedError("unexpected query parameters")
        key = request.headers.get("Idempotency-Key", "")
        if not 1 <= len(key) <= 200 or not key.isascii() or any(ord(char) < 33 for char in key):
            raise ValidationFailedError("a bounded Idempotency-Key is required")
        adapter = await adapter_for(request, current, company)
        limiter = getattr(
            request.app.state, "write_limiter", getattr(request.app.state, "pricing_limiter", None)
        )
        if limiter is not None and not limiter.allow(
            f"import:{adapter.actor.tenant_id}:{company}:{adapter.actor.user_id}",
            limit=240 if getattr(adapter, "command_group_limit", None) else 20,
        ):
            from fastapi import HTTPException

            raise HTTPException(status_code=429, detail="import write rate exceeded")
        if isinstance(adapter, ImportPreflight):
            await adapter.before_import_command(action, body, job_id)
        result = await command(
            request.app.state.session_factory, adapter, action, body, key, job_id
        )
        response = private(result.value.model_dump(mode="json"), status=result.status)
        response.headers["Idempotency-Replayed"] = str(result.replayed).lower()
        return response

    @router.get(
        "/import-definitions",
        response_model=ImportDefinitions,
        operation_id=f"list_{namespace}_import_definitions",
    )
    async def definitions(
        company_id: uuid.UUID, request: Request, current: Any = current_dependency
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                await adapter.authorize(db, write=False)
                return private(
                    {
                        "items": [
                            {"key": key, "label": label}
                            for key, label in adapter.definitions.items()
                        ],
                        "formats": ["CSV", "TSV", "XLSX"],
                        "maximum_commands": 200,
                    }
                )

    @router.post(
        "/import-templates",
        response_model=TemplateDetail,
        status_code=201,
        operation_id=f"create_{namespace}_import_template",
        dependencies=[Depends(required_key)],
    )
    async def create_template(
        company_id: uuid.UUID,
        body: TemplateRequest,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "template")

    @router.get(
        "/import-templates/{template_id}",
        response_model=TemplateDetail,
        operation_id=f"get_{namespace}_import_template",
        responses={200: {"content": FILE_CONTENT}},
    )
    async def get_template(
        company_id: uuid.UUID,
        template_id: uuid.UUID,
        request: Request,
        resource: str | None = None,
        action: str = "CREATE",
        file_format: Literal["JSON", "CSV", "TSV", "XLSX"] = Query("JSON", alias="format"),
        current: Any = current_dependency,
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                await adapter.authorize(db, write=False)
                row = await company_object(
                    db, ImportTemplateSnapshot, template_id, company_id=company_id
                )
                if row.actor_user_id != adapter.actor.user_id:
                    raise PermissionDeniedError("template belongs to another actor")
                if row.snapshot is None or row.expires_at <= utcnow():
                    raise ConflictError("template expired")
                await authorize_snapshot(db, adapter, row)
                if file_format == "JSON":
                    return private(
                        TemplateDetail(
                            id=row.id,
                            definition=row.definition,
                            fingerprint=row.fingerprint,
                            snapshot=row.snapshot,
                            expires_at=row.expires_at,
                        ).model_dump(mode="json")
                    )
                if resource is None or resource + ":" + action not in row.snapshot["schemas"]:
                    raise ValidationFailedError("choose an available template resource/action")
                content = await asyncio.to_thread(
                    template_document, row.snapshot, resource, action, file_format
                )
                return file_response(content, "import-template." + file_format.lower())

    @router.post(
        "/import-jobs",
        response_model=ImportDetail,
        status_code=201,
        operation_id=f"stage_{namespace}_import_job",
        dependencies=[Depends(required_key)],
    )
    async def stage(
        company_id: uuid.UUID,
        body: StageImport,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "stage")

    @router.get(
        "/import-jobs/{job_id}",
        response_model=ImportDetail,
        operation_id=f"get_{namespace}_import_job",
    )
    async def get_job(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                return private(
                    detail(await scoped_job(db, adapter, job_id)).model_dump(mode="json")
                )

    @router.post(
        "/import-jobs/{job_id}/validate",
        response_model=ImportDetail,
        operation_id=f"validate_{namespace}_import_job",
        dependencies=[Depends(required_key)],
    )
    async def validate(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: ImportAction,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "validate", job_id)

    @router.post(
        "/import-jobs/{job_id}/retry",
        response_model=ImportDetail,
        operation_id=f"retry_{namespace}_import_job",
        dependencies=[Depends(required_key)],
    )
    async def retry(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: ImportAction,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "retry", job_id)

    @router.post(
        "/import-jobs/{job_id}/commit",
        response_model=ImportDetail,
        operation_id=f"commit_{namespace}_import_job",
        dependencies=[Depends(required_key)],
    )
    async def commit(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: CommitImport,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "commit", job_id)

    @router.post(
        "/import-jobs/{job_id}/revisions",
        response_model=ImportDetail,
        operation_id=f"revise_{namespace}_import_job",
        dependencies=[Depends(required_key)],
    )
    async def revise(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: ReviseImport,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "revise", job_id)

    @router.post(
        "/import-jobs/{job_id}/cancel",
        response_model=ImportDetail,
        operation_id=f"cancel_{namespace}_import_job",
        dependencies=[Depends(required_key)],
    )
    async def cancel(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: ImportAction,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        return await write(request, current, company_id, body, "cancel", job_id)

    async def listing(
        request: Request,
        current: Any,
        company: uuid.UUID,
        kind: str,
        job_id: uuid.UUID | None,
        cursor: str | None,
        limit: int,
    ) -> Response:
        adapter = await adapter_for(request, current, company)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                return private(
                    await history(
                        db,
                        adapter,
                        secret(request),
                        kind=kind,
                        job_id=job_id,
                        cursor=cursor,
                        limit=limit,
                    )
                )

    @router.get(
        "/import-jobs",
        response_model=Page[ImportJobListItem],
        operation_id=f"list_{namespace}_import_jobs",
    )
    async def jobs(
        company_id: uuid.UUID,
        request: Request,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        current: Any = current_dependency,
    ) -> Response:
        return await listing(request, current, company_id, "jobs", None, cursor, limit)

    @router.get(
        "/import-jobs/{job_id}/history/{kind}",
        operation_id=f"list_{namespace}_import_history",
        response_model=Page[ImportAttemptItem | ImportArtifactItem | ImportRevisionItem],
    )
    async def job_history(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        kind: Literal["attempts", "revisions", "artifacts"],
        request: Request,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        current: Any = current_dependency,
    ) -> Response:
        return await listing(request, current, company_id, kind, job_id, cursor, limit)

    @router.get(
        "/import-jobs/{job_id}/records",
        response_model=Page[ImportRecordItem],
        operation_id=f"list_{namespace}_import_records",
    )
    async def records(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        request: Request,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        current: Any = current_dependency,
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                return private(
                    await record_history(
                        db, adapter, job_id, secret(request), cursor=cursor, limit=limit
                    )
                )

    @router.get(
        "/import-jobs/{job_id}/attempts/{attempt_id}/issues",
        response_model=Page[ImportIssueItem],
        operation_id=f"list_{namespace}_import_issues",
    )
    async def attempt_issues(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        request: Request,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        current: Any = current_dependency,
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                return private(
                    await record_history(
                        db,
                        adapter,
                        job_id,
                        secret(request),
                        attempt_id=attempt_id,
                        cursor=cursor,
                        limit=limit,
                    )
                )

    @router.post(
        "/import-jobs/{job_id}/download-ticket",
        response_model=DownloadTicket,
        operation_id=f"ticket_{namespace}_import_download",
    )
    async def ticket(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: DownloadOptions,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                job = await scoped_job(db, adapter, job_id)
                token = codec(secret(request), adapter, f"download:{job_id}").encode(
                    {"version": job.row_version, "options": body.model_dump(mode="json")}
                )
                return private(DownloadTicket(token=token).model_dump())

    @router.post(
        "/import-jobs/{job_id}/download",
        operation_id=f"download_{namespace}_import_data",
        response_class=Response,
        responses={200: {"content": FILE_CONTENT}},
    )
    async def download_data(
        company_id: uuid.UUID,
        job_id: uuid.UUID,
        body: DownloadRequest,
        request: Request,
        current: Any = current_dependency,
    ) -> Response:
        adapter = await adapter_for(request, current, company_id)
        with tenant_scope(adapter.actor.tenant_id):
            async with request.app.state.session_factory() as db:
                job = await scoped_job(db, adapter, job_id)
                options = DownloadOptions.model_validate(body.model_dump(exclude={"token"}))
                decoded = codec(secret(request), adapter, f"download:{job_id}").decode(body.token)
                if decoded != {
                    "version": job.row_version,
                    "options": options.model_dump(mode="json"),
                }:
                    raise ConflictError("download changed; request a new ticket")
                content, filename = await download(db, adapter, job_id, options)
                await db.commit()
                return file_response(content, filename)

    return router


def file_response(content: bytes, filename: str) -> Response:
    suffix = filename.rsplit(".", 1)[-1].lower()
    media = {
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(suffix, "application/octet-stream")
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
