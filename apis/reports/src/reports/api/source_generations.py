"""V2 source generation admission pins a strategy and an optional verified base."""

import uuid
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.ids import uuid7
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.api.routes import Idempotency, generation_detail
from reports.models.core import ReportGeneration
from reports.models.source_versions import (
    ReportGenerationRequest,
    ReportSourceCut,
    ReportSourceEpoch,
)
from reports.schemas.source_versions import SourceGenerationDetail, SourceGenerationRequest
from reports.tasks.access import authorize
from reports.tasks.common import audit, company_lock, get


async def detail(
    db: AsyncSession, company: uuid.UUID, identity: uuid.UUID
) -> SourceGenerationDetail:
    generation = await get(db, company, ReportGeneration, identity)
    source = await db.scalar(
        select(ReportGenerationRequest).where(
            ReportGenerationRequest.company_id == company,
            ReportGenerationRequest.generation_id == identity,
        )
    )
    if source is None:
        raise ConflictError("select a versioned generation")
    parent = (
        await get(db, company, ReportSourceCut, source.parent_cut_id)
        if source.parent_cut_id
        else None
    )
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == company,
            ReportSourceCut.generation_id == identity,
        )
    )
    return SourceGenerationDetail.model_validate(
        generation_detail(generation).model_dump()
        | {
            "strategy": source.strategy,
            "base_generation_id": parent.generation_id if parent else None,
            "verified_at": cut.created_at if cut else None,
        }
    )


@router.post("/report-generations", response_model=SourceGenerationDetail, status_code=202)
async def create_generation(
    company_id: uuid.UUID,
    body: SourceGenerationRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    authorize(current, "report.definition.manage")
    if not request.app.state.settings.source_versions_enabled:
        raise ConflictError("versioned sources are not enabled")
    from reports.tasks.enrollment import owner_for

    if await owner_for(request.app.state.settings, current.actor.tenant_id, company_id) is None:
        raise ConflictError("source owner is not configured for this company")

    async def check(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        authorize(current, "report.definition.manage")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await company_lock(db, current.actor.tenant_id, company_id)
        parent = None
        if body.base_generation_id:
            base = await get(db, company_id, ReportGeneration, body.base_generation_id)
            parent = await db.scalar(
                select(ReportSourceCut).where(
                    ReportSourceCut.company_id == company_id,
                    ReportSourceCut.generation_id == base.id,
                )
            )
            if base.status != "READY" or parent is None or parent.verification is None:
                raise ConflictError("select a verified versioned base generation")
            epoch = await get(db, company_id, ReportSourceEpoch, parent.epoch_id)
            if body.strategy == "REFRESH" and (
                epoch.status != "READY" or epoch.head_sequence != parent.sequence
            ):
                raise ConflictError("refresh requires the latest verified cut in this source epoch")
        pending = await db.scalar(
            select(ReportGenerationRequest.id)
            .join(ReportGeneration, ReportGeneration.id == ReportGenerationRequest.generation_id)
            .where(
                ReportGenerationRequest.company_id == company_id,
                ReportGeneration.status.in_(("PENDING", "BUILDING")),
            )
            .limit(1)
        )
        if pending is not None:
            raise ConflictError("a source build is already pending for this company")
        generation = ReportGeneration(
            tenant_id=current.actor.tenant_id,
            company_id=company_id,
            snapshot_id=uuid7(),
            created_by=current.actor.user_id,
        )
        db.add(generation)
        await db.flush()
        db.add(
            ReportGenerationRequest(
                tenant_id=current.actor.tenant_id,
                company_id=company_id,
                generation_id=generation.id,
                strategy=body.strategy,
                parent_cut_id=parent.id if parent else None,
            )
        )
        audit(
            db,
            current.actor.tenant_id,
            company_id,
            generation.id,
            "requested",
            current.actor.user_id,
        )
        return CommandReceipt(202, {"id": str(generation.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> SourceGenerationDetail:
        return await detail(db, company_id, uuid.UUID(refs["id"]))

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            current.actor.tenant_id,
            company_id,
            current.actor.user_id,
            "reports.v2.generation.create",
            idempotency_key,
            body.model_dump(mode="json"),
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
    return JSONResponse(result.value.model_dump(mode="json"), status_code=result.status)


@router.get("/report-generations/{identity}", response_model=SourceGenerationDetail)
async def read_generation(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
) -> SourceGenerationDetail:
    authorize(current)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            return await detail(db, company_id, identity)
