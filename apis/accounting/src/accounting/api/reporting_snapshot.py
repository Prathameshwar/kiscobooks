"""Private signed asynchronous snapshot admission and completed-page transport."""

import uuid

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, NotFoundError
from fastapi import APIRouter, Query, Request, Response
from reporting_contract.contract import FactPage
from reporting_contract.snapshots import SnapshotStatus
from sqlalchemy import func, select

from accounting.api.reporting import authorize, reply
from accounting.models.reporting_snapshot import ReportSnapshotBatch, ReportSnapshotBuild
from accounting.tasks import reporting_feed as feed

router = APIRouter(prefix="/internal/v2/reporting/{tenant_id}/{company_id}")


def status(row: ReportSnapshotBuild) -> dict[str, object]:
    return SnapshotStatus.model_validate(
        {
            "id": row.id,
            "status": row.status,
            "attempt": row.attempt,
            "completed_facts": row.completed_facts,
            "manifest": row.manifest,
            "failure_code": row.failure_code,
        }
    ).model_dump(mode="json")


# Separate service credentials replace actor auth on these private owner endpoints.
@router.post("/snapshots/{identity}", response_model=SnapshotStatus, status_code=202)
async def admit(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    if not request.app.state.settings.report_snapshot_enabled:
        raise ConflictError("asynchronous snapshots are disabled")
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            setup = await db.run_sync(lambda sync: feed.lock(sync, company_id))
            row = await db.scalar(
                select(ReportSnapshotBuild).where(
                    ReportSnapshotBuild.company_id == company_id,
                    ReportSnapshotBuild.id == identity,
                )
            )
            if row is None:
                count = await db.scalar(
                    select(func.count(ReportSnapshotBuild.id)).where(
                        ReportSnapshotBuild.company_id == company_id,
                        ReportSnapshotBuild.status.in_(("QUEUED", "RUNNING")),
                    )
                )
                if (count or 0) >= 2:
                    raise ConflictError("snapshot request queue is full")
                row = ReportSnapshotBuild(id=identity, tenant_id=tenant_id, company_id=company_id)
                db.add(row)
                await db.flush()
                await db.run_sync(
                    lambda sync: feed.evidence_audit(sync, setup, identity, "snapshot_requested")
                )
            value = status(row)
    response = reply(auth, value)
    response.status_code = 202
    return response


@router.get("/snapshots/{identity}", response_model=SnapshotStatus)
async def detail(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            row = await db.scalar(
                select(ReportSnapshotBuild).where(
                    ReportSnapshotBuild.company_id == company_id,
                    ReportSnapshotBuild.id == identity,
                )
            )
            if row is None:
                raise NotFoundError("snapshot request unavailable")
            value = status(row)
    return reply(auth, value)


@router.get("/snapshots/{identity}/facts", response_model=FactPage)
async def pages(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            row = await db.scalar(
                select(ReportSnapshotBuild).where(
                    ReportSnapshotBuild.company_id == company_id,
                    ReportSnapshotBuild.id == identity,
                )
            )
            if row is None:
                raise NotFoundError("snapshot request unavailable")
            if row.status != "COMPLETE":
                raise ConflictError("snapshot is not complete")
            # Seek one batch containing the next ordinal. A response may end at its boundary.
            batch = await db.scalar(
                select(ReportSnapshotBatch)
                .where(
                    ReportSnapshotBatch.company_id == company_id,
                    ReportSnapshotBatch.build_id == identity,
                    ReportSnapshotBatch.attempt == row.attempt,
                    ReportSnapshotBatch.first_ordinal <= after + 1,
                )
                .order_by(ReportSnapshotBatch.first_ordinal.desc())
                .limit(1)
            )
            items = []
            if batch is not None:
                start = after + 1 - batch.first_ordinal
                items = batch.facts[start : start + limit]
            end = after + len(items)
            value = {
                "manifest_id": str(identity),
                "items": items,
                "next_after": end if end < row.completed_facts else None,
            }
    return reply(auth, value)
