"""Establish one owner MVCC view under a short fence, then copy bounded pages."""

import asyncio
import datetime as dt
import hashlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from billing_platform.idempotency import canonical_json
from reporting_contract.contract import digest
from sqlalchemy import JSON, LargeBinary, String, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from accounting.config import Settings
from accounting.models.masters import AccountingSetup, Record
from accounting.models.reporting_snapshot import ReportSnapshotBatch, ReportSnapshotBuild
from accounting.models.voucher_execution import VoucherExecution
from accounting.tasks import reporting_feed as feed


async def source_batches(
    db: AsyncSession, model: type[Record], company: uuid.UUID
) -> AsyncIterator[list[Record]]:
    """Bound native payload bytes before buffering rows; avoids driver streaming buffers."""
    width: ColumnElement[int] = literal(2048)
    for column in model.__table__.columns:
        if isinstance(column.type, JSON | String | LargeBinary):
            width = width + func.coalesce(
                func.length(cast(getattr(model, column.key), LargeBinary)), 0
            )
    after = None
    while True:
        query = select(model).where(model.company_id == company)
        if model is VoucherExecution:
            query = query.where(VoucherExecution.result["outcome"].as_string() == "COMMITTED")
        if after is not None:
            query = query.where(model.id > after)
        candidates = (
            await db.execute(query.with_only_columns(model.id, width).order_by(model.id).limit(200))
        ).tuples()
        identities: list[uuid.UUID] = []
        size = 0
        for identity, byte_count in candidates:
            if identities and size + byte_count > 4 * 1024 * 1024:
                break
            if byte_count > 4 * 1024 * 1024:
                raise ValueError("native source row exceeds the snapshot memory bound")
            identities.append(identity)
            size += byte_count
        if not identities:
            return
        records = list(await db.scalars(query.where(model.id.in_(identities)).order_by(model.id)))
        after = identities[-1]
        yield records


async def get(db: AsyncSession, company: uuid.UUID, identity: uuid.UUID) -> ReportSnapshotBuild:
    row = await db.scalar(
        select(ReportSnapshotBuild)
        .where(
            ReportSnapshotBuild.company_id == company,
            ReportSnapshotBuild.id == identity,
        )
        .with_for_update()
    )
    if row is None:
        raise NotFoundError("snapshot request unavailable")
    return row


async def owned(
    db: AsyncSession,
    company: uuid.UUID,
    identity: uuid.UUID,
    attempt: int,
) -> ReportSnapshotBuild:
    row = await get(db, company, identity)
    if (
        row.status != "RUNNING"
        or row.attempt != attempt
        or row.lease_until is None
        or row.lease_until <= utcnow()
    ):
        raise ConflictError("snapshot worker no longer owns its attempt")
    return row


@asynccontextmanager
async def read_view(
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    company: uuid.UUID,
) -> AsyncIterator[tuple[AsyncSession, AccountingSetup, int, float]]:
    if engine.dialect.name not in {"mysql", "mariadb"}:
        raise ValueError("snapshot read-view requires the native database")
    # The ordinary engine remains READ COMMITTED. Only this read-only session is RR.
    readers = create_session_factory(
        engine.execution_options(isolation_level="REPEATABLE READ"), guarded=True
    )
    async with readers() as reader, reader.begin():
        async with factory() as fence, fence.begin():
            await fence.run_sync(lambda db: feed.lock(db, company))
            started = time.perf_counter()
            # This FIRST nonlocking InnoDB read establishes the view while commits are fenced.
            latest = await reader.run_sync(lambda db: feed.head(db, company))
            setup = await reader.scalar(
                select(AccountingSetup).where(AccountingSetup.company_id == company)
            )
            if setup is None:
                raise ConflictError("Accounting setup unavailable")
            sequence = latest.sequence if latest else 0
        fence_seconds = time.perf_counter() - started
        yield reader, setup, sequence, fence_seconds


async def store(
    factory: async_sessionmaker[AsyncSession],
    company: uuid.UUID,
    identity: uuid.UUID,
    attempt: int,
    first: int,
    facts: list[dict[str, Any]],
) -> None:
    async with factory() as db, db.begin():
        row = await owned(db, company, identity, attempt)
        if row.completed_facts + 1 != first:
            raise ConflictError("snapshot batch leaves a gap")
        db.add(
            ReportSnapshotBatch(
                tenant_id=row.tenant_id,
                company_id=company,
                build_id=identity,
                attempt=attempt,
                first_ordinal=first,
                fact_count=len(facts),
                content_hash=digest(facts),
                facts=facts,
            )
        )
        row.completed_facts += len(facts)
        row.lease_until = utcnow() + dt.timedelta(seconds=60)
        row.row_version += 1


async def build(
    engine: AsyncEngine,
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
    identity: uuid.UUID,
) -> None:
    factory = create_session_factory(engine, guarded=True)
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            # Serializes only claims; the source copy never holds this company fence.
            setup = await db.run_sync(lambda sync: feed.lock(sync, company))
            row = await get(db, company, identity)
            if row.status == "COMPLETE" or (
                row.status == "RUNNING" and row.lease_until and row.lease_until > utcnow()
            ):
                return
            if row.status == "QUEUED" and row.lease_until and row.lease_until > utcnow():
                return
            if row.attempt >= 3:
                if row.status != "FAILED":
                    row.status, row.lease_until, row.failure_code = (
                        "FAILED",
                        None,
                        "ATTEMPTS_EXHAUSTED",
                    )
                    await db.run_sync(
                        lambda sync: feed.evidence_audit(sync, setup, identity, "snapshot_failed")
                    )
                return
            active = await db.scalar(
                select(ReportSnapshotBuild.id)
                .where(
                    ReportSnapshotBuild.company_id == company,
                    ReportSnapshotBuild.status == "RUNNING",
                    ReportSnapshotBuild.lease_until > utcnow(),
                )
                .limit(1)
            )
            if active is not None:
                return
            row.attempt += 1
            attempt = row.attempt
            row.status, row.completed_facts, row.failure_code = "RUNNING", 0, None
            row.lease_until = utcnow() + dt.timedelta(seconds=60)
            row.row_version += 1
            await db.run_sync(
                lambda sync: feed.evidence_audit(sync, setup, identity, "snapshot_started")
            )
        started = time.perf_counter()
        dependency_ready = False
        try:
            async with asyncio.timeout(settings.report_snapshot_seconds):
                from accounting.tasks.stock_summary_source import prepare

                await prepare(factory, settings, tenant, company)
                dependency_ready = True
                async with factory() as db, db.begin():
                    await db.run_sync(lambda sync: feed.reconcile_head(sync, company))
                async with read_view(engine, factory, company) as (
                    reader,
                    setup,
                    sequence,
                    fence_time,
                ):
                    count, checksum = 0, hashlib.sha256()
                    counts: dict[str, int] = dict.fromkeys(feed.SOURCES, 0)
                    for entity, model in sorted(feed.SOURCES.items()):
                        page: list[dict[str, Any]] = []
                        byte_count = 2
                        async for records in source_batches(reader, model, company):
                            for record in records:
                                wire = feed.fact(record, entity, record.id).model_dump(mode="json")
                                raw = canonical_json(wire)
                                if len(raw) + 2 > 900000:
                                    raise ValueError("source fact exceeds transport bound")
                                if page and (
                                    len(page) == 200 or byte_count + len(raw) + 1 > 900000
                                ):
                                    await store(
                                        factory,
                                        company,
                                        identity,
                                        attempt,
                                        count - len(page) + 1,
                                        page,
                                    )
                                    page, byte_count = [], 2
                                page.append(wire)
                                byte_count += len(raw) + 1
                                checksum.update(raw + b"\n")
                                count += 1
                                counts[entity] += 1
                                if count > settings.report_snapshot_fact_limit:
                                    raise ValueError("source snapshot exceeds negotiated capacity")
                        if page:
                            await store(
                                factory, company, identity, attempt, count - len(page) + 1, page
                            )
                    result = await reader.run_sync(
                        lambda db: feed.manifest(
                            db, setup, identity, "SNAPSHOT", sequence, count, checksum.hexdigest()
                        )
                    )
                    if counts != result.control.counts:
                        raise ValueError("snapshot grains differ from same-view controls")
                async with factory() as db, db.begin():
                    row = await owned(db, company, identity, attempt)
                    if row.completed_facts != result.fact_count:
                        raise ConflictError("snapshot publication count differs")
                    row.manifest = result.model_dump(mode="json")
                    row.evidence = {
                        "isolation": "REPEATABLE READ",
                        "fence_seconds": fence_time,
                        "elapsed_seconds": time.perf_counter() - started,
                        "batch_limit": 200,
                    }
                    row.status, row.lease_until = "COMPLETE", None
                    row.row_version += 1
                    await db.run_sync(
                        lambda sync: feed.evidence_audit(sync, setup, identity, "snapshotted")
                    )
        except (Exception, asyncio.CancelledError) as exc:
            logging.getLogger(__name__).warning("Snapshot attempt stopped: %s", type(exc).__name__)
            try:
                async with factory() as db, db.begin():
                    row = await owned(db, company, identity, attempt)
                    # The failed read view expired its ORM objects. Audit from this live session.
                    failure_setup = await db.scalar(
                        select(AccountingSetup).where(AccountingSetup.company_id == company)
                    )
                    if failure_setup is None:
                        raise ConflictError("Accounting setup unavailable for snapshot failure")
                    row.status, row.lease_until = "FAILED", None
                    row.failure_code = (
                        "SNAPSHOT_CAPACITY_OR_VERIFICATION"
                        if isinstance(exc, ValueError | TimeoutError)
                        else "SNAPSHOT_INTERRUPTED"
                    )
                    # A temporary Catalog outage has not opened a read view or
                    # copied any facts. Preserve the integrity-attempt budget.
                    if not dependency_ready and isinstance(exc, httpx.HTTPError | TimeoutError):
                        row.status = "QUEUED"
                        row.attempt -= 1
                        row.lease_until = utcnow() + dt.timedelta(seconds=10)
                        row.failure_code = "DEPENDENCY_UNAVAILABLE"
                    row.row_version += 1
                    await db.run_sync(
                        lambda sync: feed.evidence_audit(
                            sync, failure_setup, identity, "snapshot_failed"
                        )
                    )
            except ConflictError:
                pass  # A replacement attempt owns the row; this worker may not alter it.
            if isinstance(exc, asyncio.CancelledError):
                raise


async def cycle_company(
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
) -> None:
    with tenant_scope(tenant):
        async with factory() as db:
            pending = list(
                await db.scalars(
                    select(ReportSnapshotBuild.id)
                    .where(
                        ReportSnapshotBuild.company_id == company,
                        or_(
                            ReportSnapshotBuild.status.in_(("QUEUED", "FAILED"))
                            & (ReportSnapshotBuild.attempt < 3)
                            & or_(
                                ReportSnapshotBuild.failure_code.is_(None),
                                ReportSnapshotBuild.failure_code.in_(
                                    ("SNAPSHOT_INTERRUPTED", "DEPENDENCY_UNAVAILABLE")
                                ),
                            ),
                            (ReportSnapshotBuild.status == "RUNNING")
                            & (ReportSnapshotBuild.lease_until <= utcnow()),
                        ),
                    )
                    .order_by(ReportSnapshotBuild.id)
                    .limit(10)
                )
            )
    for identity in pending:
        await build(engine, settings, tenant, company, identity)


async def run(settings: Settings) -> None:
    import httpx
    from reporting_contract.enrollment import discover

    if not settings.report_snapshot_enabled:
        raise ValueError("async report snapshots are disabled")
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            while True:
                try:
                    scopes = {
                        (s.tenant_id, s.company_id)
                        for key in settings.report_credentials.values()
                        for s in key.scopes
                    }
                    if settings.report_enrollment_source and any(
                        k.allow_enrolled_companies for k in settings.report_credentials.values()
                    ):
                        scopes.update(
                            (s.tenant_id, s.company_id)
                            for s in await discover(client, settings.report_enrollment_source)
                        )
                    semaphore = asyncio.Semaphore(settings.report_snapshot_parallelism)

                    async def process(
                        tenant: uuid.UUID, company: uuid.UUID, gate: asyncio.Semaphore = semaphore
                    ) -> None:
                        async with gate:
                            await cycle_company(engine, factory, settings, tenant, company)

                    await asyncio.gather(*(process(t, c) for t, c in sorted(scopes)))
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Snapshot discovery retry: %s", type(exc).__name__
                    )
                await asyncio.sleep(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(Settings.model_validate({})))
