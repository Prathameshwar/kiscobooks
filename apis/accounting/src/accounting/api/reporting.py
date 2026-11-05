"""Private request-bound signed financial export; explicit Reports company grants."""

import uuid

from billing_platform.db import tenant_scope
from billing_platform.errors import NotFoundError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    authenticate_snapshot,
    require_snapshot_scope,
    response_headers,
)
from fastapi import APIRouter, Query, Request, Response
from reporting_contract.enrollment import scope_allowed
from sqlalchemy import select

from accounting.models.reporting import (
    ReportChange,
    ReportChangeFact,
    ReportSnapshot,
    ReportSnapshotFact,
)
from accounting.tasks.reporting_feed import head, snapshot

router = APIRouter(prefix="/internal/v1/reporting/{tenant_id}/{company_id}")


async def authorize(
    request: Request, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> tuple[SnapshotCredential, bytes, str]:
    if set(request.query_params) - {"after", "limit"} or len(request.query_params) != len(
        request.query_params.multi_items()
    ):
        raise ValidationFailedError("unsupported financial export query")
    # Requests have no body. A body must not be silently ignored or read without a bound.
    async for chunk in request.stream():
        if chunk:
            raise ValidationFailedError("financial export request has no body")
    auth = authenticate_snapshot(
        request.app.state.settings.report_credentials,
        owner="accounting",
        requester="reports",
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        body=b"",
    )
    allowed = await scope_allowed(
        auth[0], request.app.state.settings.report_enrollment_source, tenant_id, company_id
    )
    require_snapshot_scope(auth[0], tenant_id=tenant_id, company_id=company_id, enrolled=allowed)
    return auth


def reply(auth: tuple[SnapshotCredential, bytes, str], value: object) -> Response:
    credential, framed, key_id = auth
    body = canonical_json(value)
    return Response(
        body,
        media_type="application/json",
        headers=response_headers(
            credential,
            owner="accounting",
            requester="reports",
            key_id=key_id,
            request_bytes=framed,
            body=body,
        ),
    )


# Service credentials replace actor auth on this private owner channel.
@router.post("/refresh-stock", include_in_schema=False)
async def refresh_stock(tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    from accounting.tasks.stock_summary_source import prepare

    with tenant_scope(tenant_id):
        await prepare(
            request.app.state.session_factory, request.app.state.settings, tenant_id, company_id
        )
    return reply(auth, {"status": "READY"})


@router.post("/snapshots/{snapshot_id}", include_in_schema=False)
async def create_snapshot(
    tenant_id: uuid.UUID, company_id: uuid.UUID, snapshot_id: uuid.UUID, request: Request
) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            result = await db.run_sync(lambda sync: snapshot(sync, company_id, snapshot_id))
    return reply(auth, result.model_dump(mode="json"))


@router.get("/head", include_in_schema=False)
async def barrier(tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            latest = await db.run_sync(lambda sync: head(sync, company_id))
            value = {
                "sequence": latest.sequence if latest else 0,
                "manifest": latest.manifest if latest else None,
            }
    return reply(auth, value)


@router.get("/changes/{sequence}", include_in_schema=False)
async def change(
    tenant_id: uuid.UUID, company_id: uuid.UUID, sequence: int, request: Request
) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            row = await db.scalar(
                select(ReportChange).where(
                    ReportChange.company_id == company_id, ReportChange.sequence == sequence
                )
            )
            if row is None:
                raise NotFoundError("committed change unavailable")
            value = row.manifest
    return reply(auth, value)


@router.get("/{kind}/{identity}/facts", include_in_schema=False)
async def pages(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    kind: str,
    identity: uuid.UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
) -> Response:
    auth = await authorize(request, tenant_id, company_id)
    if kind not in {"snapshots", "changes"}:
        raise NotFoundError("unknown export")
    model = ReportSnapshotFact if kind == "snapshots" else ReportChangeFact
    parent = ReportSnapshotFact.snapshot_id if kind == "snapshots" else ReportChangeFact.change_id
    header = ReportSnapshot if kind == "snapshots" else ReportChange
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            if (
                await db.scalar(
                    select(header.id).where(header.company_id == company_id, header.id == identity)
                )
                is None
            ):
                raise NotFoundError("export unavailable")
            rows = list(
                await db.scalars(
                    select(model)
                    .where(
                        model.company_id == company_id, parent == identity, model.ordinal > after
                    )
                    .order_by(model.ordinal)
                    .limit(limit + 1)
                )
            )
            selected: list[ReportSnapshotFact | ReportChangeFact] = []
            byte_count = 0
            for row in rows[:limit]:
                size = len(canonical_json(row.fact))
                if byte_count + size > 900000 and selected:
                    break
                selected.append(row)
                byte_count += size
            value = {
                "manifest_id": str(identity),
                "items": [row.fact for row in selected],
                "next_after": selected[-1].ordinal if len(rows) > len(selected) else None,
            }
    return reply(auth, value)
