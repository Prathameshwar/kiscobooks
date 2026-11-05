"""Indexed actor-owned history; no result blobs, exact counts or offset scans."""

import uuid
from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.listing import PageMeta
from billing_platform.pagination import CursorCodec
from fastapi import Depends, Query, Request
from sqlalchemy import select

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.api.routes import codec
from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob
from reports.models.source_versions import ReportGenerationRequest
from reports.schemas.framework import JobListItem, JobPage
from reports.schemas.requests import ListItem, ResourcePage
from reports.tasks.access import authorize, fingerprint


def position(
    request: Request, current: Access, kind: str, limit: int, cursor: str | None
) -> tuple[CursorCodec, uuid.UUID | None]:
    if set(request.query_params) - (
        {"limit", "cursor", "code"} if kind != "generations" else {"limit", "cursor"}
    ) or len(request.query_params) != len(request.query_params.multi_items()):
        raise ValidationFailedError("unsupported report list query")
    signer = codec(request, current, f"v2.list:{kind}:{limit}")
    value = signer.decode(cursor).get("id") if cursor else None
    try:
        after = uuid.UUID(value) if value is not None else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationFailedError("invalid report cursor") from exc
    return signer, after


async def jobs(
    request: Request,
    current: Access,
    kind: str,
    limit: int,
    cursor: str | None,
    code: str | None = None,
) -> JobPage:
    authorize(current, "report.export" if kind == "EXPORT" else "report.read")
    signer, after = position(request, current, kind + (":" + code if code else ""), limit, cursor)
    query = select(
        ReportJob.id,
        ReportJob.status,
        ReportJob.kind,
        ReportJob.created_at,
        ReportJob.definition["code"].as_string().label("code"),
        ReportJob.definition["permissions"].label("permissions"),
    ).where(
        ReportJob.company_id == current.context.company_id,
        ReportJob.actor_id == current.actor.user_id,
        ReportJob.kind == kind,
        ReportJob.permission_hash == fingerprint(current),
    )
    if after is not None:
        query = query.where(ReportJob.id < after)
    if code is not None:
        query = query.where(ReportJob.definition["code"].as_string() == code)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            found = list(
                (await db.execute(query.order_by(ReportJob.id.desc()).limit(limit + 1))).all()
            )
    selected, more = found[:limit], len(found) > limit
    visible = []
    for row in selected:
        try:
            for permission in row.permissions:
                current.actor.require_scope(
                    permission, target=ScopePath(company_id=current.context.company_id)
                )
        except PermissionDeniedError:
            continue
        visible.append(
            JobListItem(
                id=row.id,
                code=row.code,
                kind=row.kind,
                status=row.status,
                created_at=row.created_at,
            )
        )
    return JobPage(
        items=visible,
        page=PageMeta(
            limit=limit,
            has_more=more,
            next_cursor=signer.encode({"id": str(selected[-1].id)}) if more else None,
        ),
    )


@router.get("/report-runs", response_model=JobPage)
async def runs(
    request: Request,
    current: Annotated[Access, Depends(access)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    code: Annotated[str | None, Query(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")] = None,
) -> JobPage:
    return await jobs(request, current, "RUN", limit, cursor, code)


@router.get("/report-exports", response_model=JobPage)
async def exports(
    request: Request,
    current: Annotated[Access, Depends(access)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    code: Annotated[str | None, Query(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")] = None,
) -> JobPage:
    return await jobs(request, current, "EXPORT", limit, cursor, code)


@router.get("/report-generations", response_model=ResourcePage)
async def generations(
    request: Request,
    current: Annotated[Access, Depends(access)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> ResourcePage:
    authorize(current)
    signer, after = position(request, current, "generations", limit, cursor)
    query = (
        select(ReportGeneration.id, ReportGeneration.status, ReportGeneration.applied_sequence)
        .join(ReportGenerationRequest, ReportGenerationRequest.generation_id == ReportGeneration.id)
        .where(ReportGeneration.company_id == current.context.company_id)
    )
    if after is not None:
        query = query.where(ReportGeneration.id < after)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            found = list(
                (
                    await db.execute(query.order_by(ReportGeneration.id.desc()).limit(limit + 1))
                ).all()
            )
    selected, more = found[:limit], len(found) > limit
    return ResourcePage(
        items=[
            ListItem(id=row.id, status=row.status, applied_sequence=row.applied_sequence)
            for row in selected
        ],
        page=PageMeta(
            limit=limit,
            has_more=more,
            next_cursor=signer.encode({"id": str(selected[-1].id)}) if more else None,
        ),
    )
