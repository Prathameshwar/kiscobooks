"""Short locked job mutations and bounded publication; calculation owns no tenant lock."""

import hashlib
import uuid
from typing import Any, cast

from billing_platform.db.claims import insert_candidate
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PlatformError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reporting import jobs
from reports.models.framework import (
    ReportJob,
    ReportJobAttempt,
    ReportResultBatch,
    ReportTenantQuota,
)
from reports.tasks.common import audit, get

JOB_EVENTS = frozenset({"reports.job.short", "reports.job.bulk", "reports.job.render"})


class QuotaExceededError(PlatformError):
    status_code = 429
    code = "report_quota_exceeded"


async def quota_lock(db: AsyncSession) -> None:
    tenant = require_current_tenant()
    await insert_candidate(
        db, ReportTenantQuota, {"id": uuid7(), "tenant_id": tenant, "revision": 1}
    )
    await db.scalar(
        select(ReportTenantQuota).where(ReportTenantQuota.tenant_id == tenant).with_for_update()
    )


async def admit(db: AsyncSession, maximum_queued: int = 20) -> None:
    await quota_lock(db)
    queued = await db.scalar(select(func.count(ReportJob.id)).where(ReportJob.status == "QUEUED"))
    if (queued or 0) >= maximum_queued:
        raise QuotaExceededError("tenant report queue is full; retry later")


def dispatch(db: AsyncSession, row: ReportJob) -> None:
    emit(
        db,
        tenant_id=row.tenant_id,
        aggregate_type="reports.job",
        aggregate_id=row.id,
        event_type="reports.job." + row.lane.lower(),
        payload={"job_id": str(row.id), "company_id": str(row.company_id), "version": 1},
    )


def state(row: ReportJob) -> jobs.JobState:
    return jobs.JobState(
        cast(jobs.JobStatus, row.status), row.attempt, row.lease_until, row.available_at
    )


def assign(row: ReportJob, value: jobs.JobState) -> None:
    row.status, row.attempt, row.lease_until = value.status, value.attempt, value.lease_until
    if value.available_at is not None:
        row.available_at = value.available_at
    row.row_version += 1


async def claim(db: AsyncSession, company: uuid.UUID, identity: uuid.UUID) -> ReportJob | None:
    await quota_lock(db)
    row = await get(db, company, ReportJob, identity, lock=True)
    now = utcnow()
    if row.attempt >= 3 and row.status == "RUNNING" and row.lease_until and row.lease_until <= now:
        row.status, row.lease_until, row.failure_code = "FAILED", None, "ATTEMPTS_EXHAUSTED"
        row.row_version += 1
        await close_attempt(db, row, "EXPIRED")
        audit(db, row.tenant_id, company, row.id, "failed", row.actor_id)
        return None
    try:
        next_state = jobs.claim(state(row), now)
    except ValueError:
        return None
    count = await db.scalar(
        select(func.count(ReportJob.id)).where(
            ReportJob.kind == row.kind,
            ReportJob.status == "RUNNING",
            ReportJob.lease_until > now,
        )
    )
    if (count or 0) >= (2 if row.kind == "RUN" else 1):
        return None
    if row.attempt:
        await close_attempt(db, row, "EXPIRED")
    assign(row, next_state)
    row.completed_rows, row.result, row.failure_code = 0, None, None
    db.add(
        ReportJobAttempt(
            tenant_id=row.tenant_id,
            company_id=company,
            job_id=row.id,
            attempt=row.attempt,
        )
    )
    audit(db, row.tenant_id, company, row.id, "started", row.actor_id)
    await db.flush()
    return row


async def close_attempt(db: AsyncSession, row: ReportJob, outcome: str) -> None:
    attempt = await db.scalar(
        select(ReportJobAttempt)
        .where(
            ReportJobAttempt.company_id == row.company_id,
            ReportJobAttempt.job_id == row.id,
            ReportJobAttempt.attempt == row.attempt,
        )
        .with_for_update()
    )
    if attempt is not None and attempt.finished_at is None:
        attempt.finished_at, attempt.outcome = utcnow(), outcome


async def owned(
    db: AsyncSession, company: uuid.UUID, identity: uuid.UUID, attempt: int
) -> ReportJob:
    row = await get(db, company, ReportJob, identity, lock=True)
    try:
        jobs.require_lease(state(row), attempt, utcnow())
    except ValueError as exc:
        raise ConflictError("report worker no longer owns the attempt") from exc
    return row


async def heartbeat(
    db: AsyncSession, company: uuid.UUID, identity: uuid.UUID, attempt: int
) -> None:
    row = await owned(db, company, identity, attempt)
    assign(row, jobs.heartbeat(state(row), attempt, utcnow()))


async def append(
    db: AsyncSession,
    company: uuid.UUID,
    identity: uuid.UUID,
    attempt: int,
    first_ordinal: int,
    values: list[dict[str, Any]],
) -> None:
    row = await owned(db, company, identity, attempt)
    if row.kind != "RUN":
        raise ConflictError("only report calculations publish result rows")
    checksum = hashlib.sha256(canonical_json(values)).hexdigest()
    existing = await db.scalar(
        select(ReportResultBatch).where(
            ReportResultBatch.company_id == company,
            ReportResultBatch.job_id == identity,
            ReportResultBatch.attempt == attempt,
            ReportResultBatch.first_ordinal == first_ordinal,
        )
    )
    if existing is not None:
        if existing.content_hash != checksum or existing.rows != values:
            raise ConflictError("result batch replay differs")
        return
    if first_ordinal != row.completed_rows + 1:
        raise ConflictError("result batch would leave a gap")
    batch = ReportResultBatch(
        tenant_id=row.tenant_id,
        company_id=company,
        job_id=identity,
        attempt=attempt,
        first_ordinal=first_ordinal,
        row_count=len(values),
        content_hash=checksum,
        rows=values,
    )
    db.add(batch)
    row.completed_rows += len(values)
    assign(row, jobs.heartbeat(state(row), attempt, utcnow()))
    await db.flush()
    if row.definition["code"] == "TRIAL_BALANCE" and row.definition["version"] >= 6:
        from reports.models.hierarchy import ReportHierarchyNode

        for index, value in enumerate(values):
            if value["row_kind"] == "TRIAL_BALANCE_CONTROL":
                continue
            db.add(
                ReportHierarchyNode(
                    tenant_id=row.tenant_id,
                    company_id=company,
                    job_id=identity,
                    batch_id=batch.id,
                    attempt=attempt,
                    ordinal=first_ordinal + index,
                    **{
                        key: value[key]
                        for key in ("period", "node_key", "parent_key", "depth", "is_zero")
                    },
                )
            )
        await db.flush()


async def complete(
    db: AsyncSession,
    company: uuid.UUID,
    identity: uuid.UUID,
    attempt: int,
    result: dict[str, Any],
) -> None:
    row = await owned(db, company, identity, attempt)
    pinned = result.get("plan", {}).get("mode") == "PINNED_QUERY"
    if pinned and (
        row.kind != "RUN"
        or row.completed_rows
        or result.get("row_count") is not None
        or result.get("content_hash") is not None
    ):
        raise ConflictError("pinned results cannot claim materialized rows or content")
    if not pinned and result.get("row_count") != row.completed_rows:
        raise ConflictError("published result count differs from durable batches")
    if (
        row.kind == "RUN"
        and row.definition["code"] == "TRIAL_BALANCE"
        and row.definition["version"] == 6
    ):
        from reports.models.hierarchy import ReportHierarchyNode

        controls = result.get("evidence", {}).get("trial_balance", {}).get("periods", {})
        count = await db.scalar(
            select(func.count(ReportHierarchyNode.id)).where(
                ReportHierarchyNode.company_id == company,
                ReportHierarchyNode.job_id == identity,
                ReportHierarchyNode.attempt == attempt,
            )
        )
        if not controls or count != row.completed_rows - len(controls):
            raise ConflictError("published Trial Balance hierarchy is incomplete")
    row.result = result
    assign(row, jobs.finish(state(row), attempt, utcnow()))
    await close_attempt(db, row, "COMPLETE")
    audit(db, row.tenant_id, company, identity, "completed", row.actor_id)


async def fail(
    db: AsyncSession,
    company: uuid.UUID,
    identity: uuid.UUID,
    attempt: int,
    code: str,
    *,
    blocked: bool = False,
) -> None:
    row = await owned(db, company, identity, attempt)
    assign(row, jobs.finish(state(row), attempt, utcnow(), "BLOCKED" if blocked else "FAILED"))
    row.failure_code = code
    await close_attempt(db, row, row.status)
    audit(db, row.tenant_id, company, identity, "blocked" if blocked else "failed", row.actor_id)


async def cancel(db: AsyncSession, row: ReportJob) -> None:
    if row.status == "CANCELLED":
        return
    try:
        assign(row, jobs.cancel(state(row)))
    except ValueError as exc:
        raise ConflictError("report job cannot be cancelled") from exc
    await close_attempt(db, row, "CANCELLED")
    audit(db, row.tenant_id, row.company_id, row.id, "cancelled", row.actor_id)


async def retry(db: AsyncSession, company: uuid.UUID, identity: uuid.UUID) -> None:
    await admit(db)
    row = await get(db, company, ReportJob, identity, lock=True)
    try:
        next_state = jobs.retry(state(row), utcnow())
    except ValueError as exc:
        raise ConflictError("report job cannot be retried") from exc
    assign(row, next_state)
    dispatch(db, row)
    audit(db, row.tenant_id, row.company_id, row.id, "retried", row.actor_id)
