import datetime as dt
import uuid
from dataclasses import replace

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, USER
from sqlalchemy import func, select
from test_foundation import generation, load

from reports.domain.reporting import jobs as state
from reports.models.core import ReportGeneration
from reports.models.framework import (
    FRAMEWORK_MODELS,
    ReportJob,
    ReportJobAttempt,
    ReportResultBatch,
)
from reports.tasks import framework_jobs as jobs
from reports.tasks.common import get


def test_pure_job_leases_fence_late_workers_and_terminal_results():
    now = utcnow()
    queued = state.JobState("QUEUED")
    running = state.claim(queued, now)
    assert running.attempt == 1
    assert state.heartbeat(running, 1, now).lease_until > now
    with pytest.raises(ValueError):
        state.claim(running, now)
    later = state.claim(running, now + dt.timedelta(seconds=60))
    assert later.attempt == 2
    with pytest.raises(ValueError):
        state.require_lease(later, 1, now)
    with pytest.raises(ValueError):
        state.require_lease(running, 1, running.lease_until)
    complete = state.finish(running, 1, now)
    for operation in (lambda: state.claim(complete, now), lambda: state.cancel(complete)):
        with pytest.raises(ValueError):
            operation()
    cancelled = state.cancel(running)
    assert state.cancel(cancelled) == cancelled
    failed = state.finish(running, 1, now, "FAILED")
    retry = state.retry(failed, now)
    with pytest.raises(ValueError):
        state.claim(retry, now)
    assert state.claim(retry, now + dt.timedelta(seconds=3)).attempt == 2
    for invalid in (replace(failed, attempt=3), complete):
        with pytest.raises(ValueError):
            state.retry(invalid, now)
    for operation in (
        lambda: state.claim(queued, now, lease_seconds=1),
        lambda: state.claim(queued, now.replace(tzinfo=None)),
        lambda: state.heartbeat(running, 1, now, 301),
        lambda: state.finish(running, 1, now, "QUEUED"),
        lambda: state.require_lease(replace(running, lease_until=None), 1, now),
    ):
        with pytest.raises(ValueError):
            operation()


async def new_job(
    app, generation_id, *, tenant=TENANT, company=COMPANY, kind="RUN", parent_id=None
):
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            await jobs.admit(db)
            row = ReportJob(
                tenant_id=tenant,
                company_id=company,
                generation_id=generation_id,
                actor_id=USER,
                kind=kind,
                lane="SHORT",
                parent_id=parent_id,
                definition={"code": "SOURCE_RECONCILIATION", "version": 2},
                parameters={},
                display={},
                permission_hash="a" * 64,
                request_hash="b" * 64,
            )
            db.add(row)
            await db.flush()
            jobs.dispatch(db, row)
            return row.id


async def test_bounded_results_replay_gap_fencing_and_independent_export(app, client, prefix):
    created = await generation(client, prefix)
    await load(app, created["id"])
    identity = await new_job(app, uuid.UUID(created["id"]))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await jobs.claim(db, COMPANY, identity)
            assert row.attempt == 1
        async with app.state.session_factory() as db, db.begin():
            assert await jobs.claim(db, COMPANY, identity) is None
        values = [{"amount": "123.0000", "currency": "INR"}]
        for _ in range(2):
            async with app.state.session_factory() as db, db.begin():
                await jobs.append(db, COMPANY, identity, 1, 1, values)
        for first, data in ((1, [{"amount": "999"}]), (3, values)):
            with pytest.raises(ConflictError):
                async with app.state.session_factory() as db, db.begin():
                    await jobs.append(db, COMPANY, identity, 1, first, data)
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                await jobs.complete(db, COMPANY, identity, 1, {"row_count": 2})
        with pytest.raises(ConflictError, match="pinned"):
            async with app.state.session_factory() as db, db.begin():
                await jobs.complete(
                    db, COMPANY, identity, 1, {"plan": {"mode": "PINNED_QUERY"}, "row_count": None}
                )
        async with app.state.session_factory() as db, db.begin():
            await jobs.complete(db, COMPANY, identity, 1, {"row_count": 1})
        async with app.state.session_factory() as db:
            row = await get(db, COMPANY, ReportJob, identity)
            assert row.status == "COMPLETE" and row.result == {"row_count": 1}
            assert await db.scalar(select(func.count(ReportResultBatch.id))) == 1
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                await jobs.append(db, COMPANY, identity, 1, 2, values)
        export = await new_job(app, uuid.UUID(created["id"]), kind="EXPORT", parent_id=identity)
        async with app.state.session_factory() as db, db.begin():
            row = await jobs.claim(db, COMPANY, export)
            assert row.kind == "EXPORT"
            await jobs.fail(db, COMPANY, export, 1, "STORAGE_UNAVAILABLE")
        async with app.state.session_factory() as db:
            assert (await get(db, COMPANY, ReportJob, identity)).status == "COMPLETE"


async def test_expired_attempt_retry_and_cancellation_preserve_evidence(app, client, prefix):
    created = await generation(client, prefix)
    identity = await new_job(app, uuid.UUID(created["id"]))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await jobs.claim(db, COMPANY, identity)
            await jobs.append(db, COMPANY, identity, 1, 1, [{"old": True}])
        async with app.state.session_factory() as db, db.begin():
            row = await get(db, COMPANY, ReportJob, identity, lock=True)
            row.lease_until = utcnow() - dt.timedelta(seconds=1)
        async with app.state.session_factory() as db, db.begin():
            assert (await jobs.claim(db, COMPANY, identity)).attempt == 2
            await jobs.heartbeat(db, COMPANY, identity, 2)
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                await jobs.append(db, COMPANY, identity, 1, 2, [{"late": True}])
        async with app.state.session_factory() as db, db.begin():
            await jobs.fail(db, COMPANY, identity, 2, "TRANSIENT")
        async with app.state.session_factory() as db, db.begin():
            await jobs.retry(db, COMPANY, identity)
        async with app.state.session_factory() as db, db.begin():
            row = await get(db, COMPANY, ReportJob, identity, lock=True)
            await jobs.cancel(db, row)
            await jobs.cancel(db, row)
        async with app.state.session_factory() as db:
            assert (await get(db, COMPANY, ReportJob, identity)).status == "CANCELLED"
            assert await db.scalar(select(func.count(ReportResultBatch.id))) == 1
            assert await db.scalar(select(func.count(ReportJobAttempt.id))) == 2


async def test_tenant_quota_allows_two_runs_and_all_framework_tables_are_isolated(
    app, client, prefix
):
    created = await generation(client, prefix)
    ids = [await new_job(app, uuid.UUID(created["id"])) for _ in range(3)]
    with tenant_scope(TENANT):
        for index, identity in enumerate(ids):
            async with app.state.session_factory() as db, db.begin():
                claimed = await jobs.claim(db, COMPANY, identity)
                assert (claimed is not None) == (index < 2)
        async with app.state.session_factory() as db, db.begin():
            await jobs.append(db, COMPANY, ids[0], 1, 1, [{"tenant": "first"}])
        with pytest.raises(jobs.QuotaExceededError):
            async with app.state.session_factory() as db, db.begin():
                await jobs.admit(db, maximum_queued=1)
    other = uuid.uuid4()
    with tenant_scope(other):
        async with app.state.session_factory() as db, db.begin():
            for model in FRAMEWORK_MODELS:
                assert await db.scalar(select(func.count(model.id))) == 0
            source = ReportGeneration(tenant_id=other, company_id=COMPANY, snapshot_id=uuid.uuid4())
            db.add(source)
            await db.flush()
            source_id = source.id
        foreign = await new_job(app, source_id, tenant=other)
        async with app.state.session_factory() as db, db.begin():
            await jobs.claim(db, COMPANY, foreign)
            await jobs.append(db, COMPANY, foreign, 1, 1, [{"tenant": "other"}])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportJob.id))) == 3
            assert [row.rows for row in await db.scalars(select(ReportResultBatch))] == [
                [{"tenant": "first"}]
            ]
        for model in (ReportJob, ReportJobAttempt, ReportResultBatch):
            with pytest.raises(ConflictError):
                async with app.state.session_factory() as db, db.begin():
                    row = await db.scalar(select(model).limit(1))
                    await db.delete(row)


@pytest.mark.mysql
async def test_independent_same_company_job_claim_does_not_wait_for_a_running_job_lock(
    app, client, prefix, engine
):
    import asyncio

    if engine.dialect.name != "mysql":
        pytest.skip("native row-lock concurrency")
    created = await generation(client, prefix)
    first = await new_job(app, uuid.UUID(created["id"]))
    second = await new_job(app, uuid.UUID(created["id"]))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await jobs.claim(db, COMPANY, first)

        async def another_claim():
            async with app.state.session_factory() as other, other.begin():
                return (await jobs.claim(other, COMPANY, second)).attempt

        async with app.state.session_factory() as locked, locked.begin():
            await jobs.owned(locked, COMPANY, first, 1)
            assert await asyncio.wait_for(another_claim(), 5) == 1


@pytest.mark.parametrize("target", ["job", "attempt"])
async def test_terminal_job_and_attempt_remain_immutable_after_attribute_expiry(
    app, client, prefix, target
):
    created = await generation(client, prefix)
    identity = await new_job(app, uuid.UUID(created["id"]))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await jobs.claim(db, COMPANY, identity)
            await jobs.complete(db, COMPANY, identity, 1, {"row_count": 0})
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                if target == "job":
                    row = await get(db, COMPANY, ReportJob, identity)
                    db.expire(row, ["status"])
                    row.status = "RUNNING"
                else:
                    row = await db.scalar(
                        select(ReportJobAttempt).where(ReportJobAttempt.job_id == identity)
                    )
                    db.expire(row, ["finished_at"])
                    row.finished_at = None
