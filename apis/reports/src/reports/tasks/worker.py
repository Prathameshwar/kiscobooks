"""Restartable pull-based ingestion and report rendering; all network I/O outside SQL."""

import asyncio
import logging
import uuid

import httpx
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.diagnostics import log_failure
from billing_platform.errors import ConflictError, PlatformError
from reporting_contract.contract import FactPage, HeadBarrier, Manifest
from reporting_contract.transport import Owner, request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.models import core as m
from reports.models.source_versions import ReportGenerationRequest
from reports.tasks import ingest, runs
from reports.tasks.common import audit, company_lock, get


async def transfer(
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    owner: Owner,
    tenant: uuid.UUID,
    company: uuid.UUID,
    generation_id: uuid.UUID,
    manifest: Manifest,
) -> None:
    base = f"/internal/v1/reporting/{tenant}/{company}"
    while True:
        with tenant_scope(tenant):
            async with factory() as db, db.begin():
                await company_lock(db, tenant, company)
                generation = await get(db, company, m.ReportGeneration, generation_id, lock=True)
                row = await ingest.bundle(db, generation, manifest)
                if row.status == "APPLIED":
                    return
                after = row.last_ordinal
                bundle_id = row.id
        # An empty snapshot still has a signed terminal page.
        page = FactPage.model_validate(
            await request(
                client,
                owner,
                "GET",
                base
                + f"/{'snapshots' if manifest.kind=='SNAPSHOT' else 'changes'}/{manifest.id}/facts",
                {"after": str(after), "limit": "200"},
            )
        )
        with tenant_scope(tenant):
            async with factory() as db, db.begin():
                await company_lock(db, tenant, company)
                generation = await get(db, company, m.ReportGeneration, generation_id, lock=True)
                row = await get(db, company, m.ReportBundle, bundle_id, lock=True)
                if row.status == "APPLIED":
                    return
                await ingest.stage(db, row, page, after)
                await db.flush()
                if page.next_after is None:
                    await ingest.apply(db, generation, row)
                    return


async def synchronize(
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    owner: Owner,
    tenant: uuid.UUID,
    company: uuid.UUID,
    generation_id: uuid.UUID,
) -> None:
    if not any(scope.tenant_id == tenant and scope.company_id == company for scope in owner.scopes):
        raise ConflictError("report owner scope unavailable")
    base = f"/internal/v1/reporting/{tenant}/{company}"
    with tenant_scope(tenant):
        async with factory() as db:
            generation = await get(db, company, m.ReportGeneration, generation_id)
            if generation.status == "READY":
                return
            if generation.status not in {"PENDING", "BUILDING"}:
                raise ConflictError("generation is quarantined")
            snapshot_id = generation.snapshot_id
            initial = generation.manifest is None
    if initial:
        manifest = Manifest.model_validate(
            await request(client, owner, "POST", base + f"/snapshots/{snapshot_id}")
        )
        await transfer(factory, client, owner, tenant, company, generation_id, manifest)
    with tenant_scope(tenant):
        async with factory() as db:
            generation = await get(db, company, m.ReportGeneration, generation_id)
            target = generation.target_sequence
    if target is None:
        barrier = HeadBarrier.model_validate(await request(client, owner, "GET", base + "/head"))
        if barrier.manifest and (barrier.manifest.tenant_id, barrier.manifest.company_id) != (
            tenant,
            company,
        ):
            raise ConflictError("source barrier scope differs")
        with tenant_scope(tenant):
            async with factory() as db, db.begin():
                await company_lock(db, tenant, company)
                generation = await get(db, company, m.ReportGeneration, generation_id, lock=True)
                if barrier.sequence < generation.applied_sequence:
                    raise ConflictError("source barrier regressed")
                if generation.target_sequence is None:
                    generation.target_sequence = barrier.sequence
                target = generation.target_sequence
    for _ in range(1000):
        with tenant_scope(tenant):
            async with factory() as db:
                generation = await get(db, company, m.ReportGeneration, generation_id)
                after = generation.applied_sequence
        if after == target:
            break
        if after > target:
            raise ConflictError("catch-up passed its frozen barrier")
        manifest = Manifest.model_validate(
            await request(client, owner, "GET", base + f"/changes/{after+1}")
        )
        if manifest.kind != "CHANGE" or manifest.sequence != after + 1:
            raise ConflictError("source change identity differs")
        await transfer(factory, client, owner, tenant, company, generation_id, manifest)
    else:
        return  # Keep durable progress; the next poll continues this same generation.
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            await company_lock(db, tenant, company)
            generation = await get(db, company, m.ReportGeneration, generation_id, lock=True)
            await ingest.activate(db, generation)


async def poll(
    factory: async_sessionmaker[AsyncSession], client: httpx.AsyncClient, owner: Owner
) -> None:
    for scope in owner.scopes:
        tenant, company = scope.tenant_id, scope.company_id
        with tenant_scope(tenant):
            async with factory() as db:
                ids = list(
                    await db.scalars(
                        select(m.ReportGeneration.id)
                        .where(
                            m.ReportGeneration.company_id == company,
                            m.ReportGeneration.status.in_(["PENDING", "BUILDING"]),
                            m.ReportGeneration.id.not_in(
                                select(ReportGenerationRequest.generation_id)
                            ),
                        )
                        .order_by(m.ReportGeneration.id)
                        .limit(10)
                    )
                )
        for identity in ids:
            try:
                await synchronize(factory, client, owner, tenant, company, identity)
            except httpx.HTTPError as exc:
                log_failure(
                    logging.getLogger("reports.worker"),
                    service="reports",
                    event="owner.retry",
                    error=exc,
                )
            except (PlatformError, ValueError) as exc:
                with tenant_scope(tenant):
                    async with factory() as db, db.begin():
                        await company_lock(db, tenant, company)
                        generation = await get(db, company, m.ReportGeneration, identity, lock=True)
                        if generation.status in {"PENDING", "BUILDING"}:
                            generation.status = "QUARANTINED"
                            generation.failure_code = "SOURCE_VERIFICATION_FAILED"
                            audit(db, tenant, company, identity, "quarantined")
                log_failure(
                    logging.getLogger("reports.worker"),
                    service="reports",
                    event="owner.quarantined",
                    error=exc,
                )
        with tenant_scope(tenant):
            async with factory() as db:
                ids = list(
                    await db.scalars(
                        select(m.ReportRun.id)
                        .where(m.ReportRun.company_id == company, m.ReportRun.status == "PENDING")
                        .order_by(m.ReportRun.id)
                        .limit(20)
                    )
                )
            for identity in ids:
                try:
                    async with factory() as db, db.begin():
                        run = await get(db, company, m.ReportRun, identity, lock=True)
                        await runs.complete(db, run)
                except (PlatformError, ValueError) as exc:
                    async with factory() as db, db.begin():
                        run = await get(db, company, m.ReportRun, identity, lock=True)
                        if run.status == "PENDING":
                            run.status = "BLOCKED"
                            run.failure_code = "REPORT_VERIFICATION_FAILED"
                            audit(db, tenant, company, identity, "blocked")
                    log_failure(
                        logging.getLogger("reports.worker"),
                        service="reports",
                        event="run.blocked",
                        error=exc,
                    )


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            while True:
                for owner in settings.owners:
                    await poll(factory, client, owner)
                await asyncio.sleep(10)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    import dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    if args.env_file:
        dotenv.load_dotenv(args.env_file)
    asyncio.run(run(Settings.model_validate({})))
