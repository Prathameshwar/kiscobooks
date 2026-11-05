"""Restartable v2 source replication; owner network calls never hold a database lock."""

import asyncio
import hashlib
import logging
import uuid

import httpx
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import ConflictError, PlatformError
from billing_platform.idempotency import canonical_json
from reporting_contract.contract import FACT_MODELS, FactPage, HeadBarrier, Manifest
from reporting_contract.snapshots import SnapshotStatus
from reporting_contract.transport import Owner, request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.models.core import ReportBundle, ReportGeneration
from reports.models.source_versions import (
    ReportFactVersion,
    ReportGenerationRequest,
    ReportSourceCut,
    ReportSourceEpoch,
)
from reports.queries.source_versions import SourceView
from reports.tasks import source_versions as versions
from reports.tasks.common import audit, company_lock, get
from reports.tasks.source_publication import publish


async def source_request(
    db: AsyncSession, company: uuid.UUID, generation: uuid.UUID
) -> ReportGenerationRequest:
    row = await db.scalar(
        select(ReportGenerationRequest)
        .where(
            ReportGenerationRequest.company_id == company,
            ReportGenerationRequest.generation_id == generation,
        )
        .with_for_update()
    )
    if row is None:
        raise ConflictError("versioned source request is unavailable")
    return row


async def transfer(
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    owner: Owner,
    tenant: uuid.UUID,
    company: uuid.UUID,
    generation_id: uuid.UUID,
    epoch_id: uuid.UUID,
    manifest: Manifest,
) -> bool:
    base = f"/internal/{'v2' if manifest.kind == 'SNAPSHOT' else 'v1'}/reporting/{tenant}/{company}"
    for _ in range(10):
        async with factory() as db, db.begin():
            generation = await get(db, company, ReportGeneration, generation_id, lock=True)
            bundle = await versions.bundle(db, generation, manifest)
            if bundle.status == "APPLIED":
                return True
            after, bundle_id = bundle.last_ordinal, bundle.id
        page = FactPage.model_validate(
            await request(
                client,
                owner,
                "GET",
                base
                + f"/{'snapshots' if manifest.kind == 'SNAPSHOT' else 'changes'}"
                + f"/{manifest.id}/facts",
                {"after": str(after), "limit": "200"},
            )
        )
        async with factory() as db, db.begin():
            await get(db, company, ReportGeneration, generation_id, lock=True)
            epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
            if epoch.active_generation_id != generation_id:
                raise ConflictError("source writer is fenced")
            bundle = await get(db, company, ReportBundle, bundle_id, lock=True)
            await versions.stage(db, epoch, bundle, page, after)
            if page.next_after is None:
                await versions.finish(db, epoch, bundle)
                return True
    return False  # Yield admission time to other companies; resume from durable page progress.


async def completed_cut(
    factory: async_sessionmaker[AsyncSession],
    company: uuid.UUID,
    generation_id: uuid.UUID,
    epoch_id: uuid.UUID,
    manifest: Manifest,
) -> uuid.UUID:
    async with factory() as db, db.begin():
        prior = await db.scalar(
            select(ReportSourceCut).where(
                ReportSourceCut.company_id == company,
                ReportSourceCut.generation_id == generation_id,
            )
        )
        if prior is not None:
            return prior.id
        generation = await get(db, company, ReportGeneration, generation_id, lock=True)
        epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
        return (await versions.pin(db, epoch, generation, manifest)).id


async def compact(
    factory: async_sessionmaker[AsyncSession],
    company: uuid.UUID,
    generation_id: uuid.UUID,
) -> None:
    async with factory() as db:
        generation = await get(db, company, ReportGeneration, generation_id)
        source = await source_request(db, company, generation_id)
        if source.parent_cut_id is None:
            raise ConflictError("compaction needs a verified source cut")
        parent = await get(db, company, ReportSourceCut, source.parent_cut_id)
        if parent.verification is None:
            raise ConflictError("compaction source is not verified")
        view = SourceView(company, parent.epoch_id, parent.sequence)
        owner_manifest = Manifest.model_validate(parent.manifest)
        retained = await db.scalar(
            select(ReportBundle).where(
                ReportBundle.company_id == company,
                ReportBundle.generation_id == generation_id,
                ReportBundle.source_id == generation.snapshot_id,
            )
        )
        if retained is not None:
            physical = Manifest.model_validate(retained.manifest)
            count = physical.fact_count
        else:
            checksum, count = hashlib.sha256(), 0
            for entity in sorted(FACT_MODELS):
                async for rows in view.pages(db, entity):
                    for row in rows:
                        checksum.update(
                            canonical_json(versions.fact(row).model_dump(mode="json")) + b"\n"
                        )
                        count += 1
            physical = owner_manifest.model_copy(
                update={
                    "id": generation.snapshot_id,
                    "kind": "SNAPSHOT",
                    "fact_count": count,
                    "facts_hash": checksum.hexdigest(),
                }
            )
    async with factory() as db, db.begin():
        await company_lock(db, parent.tenant_id, company)
        source = await source_request(db, company, generation_id)
        generation = await get(db, company, ReportGeneration, generation_id, lock=True)
        if source.epoch_id is None:
            epoch = await versions.new_epoch(db, generation, physical)
            source.epoch_id = epoch.id
            epoch.active_generation_id = generation_id
            generation.status = "BUILDING"
        else:
            epoch = await get(db, company, ReportSourceEpoch, source.epoch_id, lock=True)
        bundle = await versions.bundle(db, generation, physical)
        epoch_id, bundle_id, durable_after = epoch.id, bundle.id, bundle.last_ordinal
        resume = None
        if durable_after:
            resume = (
                await db.execute(
                    select(ReportFactVersion.entity, ReportFactVersion.source_id).where(
                        ReportFactVersion.company_id == company,
                        ReportFactVersion.bundle_id == bundle_id,
                        ReportFactVersion.ordinal == durable_after,
                    )
                )
            ).one_or_none()
            if resume is None:
                raise ConflictError("compaction checkpoint source row is unavailable")
    after, copied = durable_after, 0
    async with factory() as reader:
        for entity in sorted(FACT_MODELS):
            if resume is not None and entity < resume[0]:
                continue
            boundary = resume[1] if resume is not None and entity == resume[0] else None
            async for rows in view.pages(reader, entity, after_source=boundary):
                end = after + len(rows)
                async with factory() as db, db.begin():
                    await get(db, company, ReportGeneration, generation_id, lock=True)
                    epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
                    if epoch.active_generation_id != generation_id:
                        raise ConflictError("compaction writer is fenced")
                    bundle = await get(db, company, ReportBundle, bundle_id, lock=True)
                    await versions.stage(
                        db,
                        epoch,
                        bundle,
                        FactPage(
                            manifest_id=physical.id,
                            items=[versions.fact(row) for row in rows],
                            next_after=end if end < count else None,
                        ),
                        after,
                    )
                copied += 1
                if copied == 10 and end < count:
                    return
                after = end
    async with factory() as db, db.begin():
        generation = await get(db, company, ReportGeneration, generation_id, lock=True)
        epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
        bundle = await get(db, company, ReportBundle, bundle_id, lock=True)
        await versions.finish(db, epoch, bundle)
        # Preserve owner evidence separately from the internal compaction receipt.
        generation.manifest = owner_manifest.model_dump(mode="json")
    cut_id = await completed_cut(factory, company, generation_id, epoch_id, owner_manifest)
    await publish(factory, company, cut_id)


async def synchronize(
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    owner: Owner,
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
    generation_id: uuid.UUID,
) -> None:
    if not any(scope.tenant_id == tenant and scope.company_id == company for scope in owner.scopes):
        raise ConflictError("report owner scope unavailable")
    with tenant_scope(tenant):
        async with factory() as db:
            generation = await get(db, company, ReportGeneration, generation_id)
            if generation.status == "READY":
                return
            if generation.status not in {"PENDING", "BUILDING"}:
                raise ConflictError("generation is quarantined")
            source = await source_request(db, company, generation_id)
            snapshot_id, initial = generation.snapshot_id, generation.manifest is None
            strategy = source.strategy
        if strategy == "COMPACT":
            await compact(factory, company, generation_id)
            return
        if initial:
            if strategy == "FRESH":
                status = SnapshotStatus.model_validate(
                    await request(
                        client,
                        owner,
                        "POST",
                        f"/internal/v2/reporting/{tenant}/{company}/snapshots/{snapshot_id}",
                    )
                )
                if status.id != snapshot_id:
                    raise ConflictError("owner snapshot identity differs")
                if status.status == "FAILED":
                    if status.attempt < 3 and status.failure_code == "SNAPSHOT_INTERRUPTED":
                        return  # The owner retries this private attempt; no partial facts are read.
                    raise ConflictError("owner snapshot failed")
                if status.status != "COMPLETE" or status.manifest is None:
                    return
                manifest = status.manifest
            else:
                async with factory() as db:
                    if source.parent_cut_id is None:
                        raise ConflictError("refresh needs a verified source cut")
                    parent = await get(db, company, ReportSourceCut, source.parent_cut_id)
                    manifest = Manifest.model_validate(parent.manifest)
            capacity(manifest, settings)
            async with factory() as db, db.begin():
                await company_lock(db, tenant, company)
                source = await source_request(db, company, generation_id)
                generation = await get(db, company, ReportGeneration, generation_id, lock=True)
                if source.epoch_id is None:
                    if strategy == "FRESH":
                        epoch = await versions.new_epoch(db, generation, manifest)
                    else:
                        epoch = await get(
                            db, company, ReportSourceEpoch, parent.epoch_id, lock=True
                        )
                        if epoch.head_sequence != parent.sequence or epoch.status != "READY":
                            raise ConflictError("refresh base is no longer the latest source cut")
                        if epoch.active_generation_id not in {None, generation_id}:
                            return
                        generation.manifest = parent.manifest
                        generation.applied_sequence = parent.sequence
                        generation.status = "BUILDING"
                    if epoch.active_generation_id not in {None, generation_id}:
                        return
                    source.epoch_id, epoch.active_generation_id = epoch.id, generation_id
                    generation.status = "BUILDING"
                    audit(db, tenant, company, generation_id, "started")
                epoch_id = source.epoch_id
            if strategy == "FRESH":
                if not await transfer(
                    factory, client, owner, tenant, company, generation_id, epoch_id, manifest
                ):
                    return
        async with factory() as db:
            source = await source_request(db, company, generation_id)
            generation = await get(db, company, ReportGeneration, generation_id)
            if source.epoch_id is None or generation.manifest is None:
                raise ConflictError("source generation has no base receipt")
            epoch_id, target = source.epoch_id, generation.target_sequence
        base = f"/internal/v1/reporting/{tenant}/{company}"
        if target is None:
            head = HeadBarrier.model_validate(await request(client, owner, "GET", base + "/head"))
            if head.manifest is not None:
                capacity(head.manifest, settings)
                if head.manifest.sequence != head.sequence:
                    raise ConflictError("source barrier sequence differs")
                if (head.manifest.tenant_id, head.manifest.company_id) != (tenant, company):
                    raise ConflictError("owner barrier scope differs")
            async with factory() as db, db.begin():
                generation = await get(db, company, ReportGeneration, generation_id, lock=True)
                if head.sequence < generation.applied_sequence:
                    raise ConflictError("source barrier regressed")
                if generation.target_sequence is None:
                    generation.target_sequence = head.sequence
                    source = await source_request(db, company, generation_id)
                    source.target_manifest = (
                        head.manifest.model_dump(mode="json") if head.manifest else None
                    )
                target = generation.target_sequence
        transferred = 0
        for _ in range(1000):
            async with factory() as db:
                generation = await get(db, company, ReportGeneration, generation_id)
                after = generation.applied_sequence
            if after == target:
                break
            if after > target:
                raise ConflictError("source passed the pinned barrier")
            if transferred >= 1000:
                return
            from reports.tasks.source_prefetch import append_available

            appended = await append_available(
                factory,
                client,
                owner,
                settings,
                tenant,
                company,
                generation_id,
                epoch_id,
                after,
                min(target, after + 1000 - transferred),
            )
            if appended:
                transferred += appended
                continue
            manifest = Manifest.model_validate(
                await request(client, owner, "GET", base + f"/changes/{after + 1}")
            )
            capacity(manifest, settings)
            if manifest.kind != "CHANGE" or manifest.sequence != after + 1:
                raise ConflictError("source change identity differs")
            if not await transfer(
                factory, client, owner, tenant, company, generation_id, epoch_id, manifest
            ):
                return
            transferred += 1
        else:
            return
        assert generation.manifest is not None
        final_manifest = Manifest.model_validate(generation.manifest)
        async with factory() as db:
            source = await source_request(db, company, generation_id)
            barrier = (
                Manifest.model_validate(source.target_manifest) if source.target_manifest else None
            )
        if barrier is not None:
            if any(
                getattr(final_manifest, key) != getattr(barrier, key)
                for key in (
                    "tenant_id",
                    "company_id",
                    "sequence",
                    "generation",
                    "schema_hash",
                    "scope_hash",
                    "permission_hash",
                    "control",
                )
            ) or (final_manifest.kind == "CHANGE" and final_manifest != barrier):
                raise ConflictError("completed source receipt differs from its pinned barrier")
        cut = await completed_cut(factory, company, generation_id, epoch_id, final_manifest)
        await publish(factory, company, cut)


def capacity(manifest: Manifest, settings: Settings) -> None:
    if max(manifest.fact_count, sum(manifest.control.counts.values())) > settings.source_fact_limit:
        raise ConflictError("source exceeds the enabled versioned capacity")


async def cycle(
    settings: Settings,
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
) -> None:
    for owner in settings.owners:
        for scope in owner.scopes:
            if settings.automatic_sources_enabled:
                from reports.tasks.automatic_sources import reconcile

                await reconcile(factory, client, owner, scope.tenant_id, scope.company_id)
            with tenant_scope(scope.tenant_id):
                async with factory() as db:
                    identities = list(
                        await db.scalars(
                            select(ReportGeneration.id)
                            .join(
                                ReportGenerationRequest,
                                ReportGenerationRequest.generation_id == ReportGeneration.id,
                            )
                            .where(
                                ReportGeneration.company_id == scope.company_id,
                                ReportGeneration.status.in_(("PENDING", "BUILDING")),
                            )
                            .order_by(ReportGeneration.id)
                            .limit(10)
                        )
                    )
                for identity in identities:
                    try:
                        await synchronize(
                            factory,
                            client,
                            owner,
                            settings,
                            scope.tenant_id,
                            scope.company_id,
                            identity,
                        )
                    except (PlatformError, ValueError):
                        async with factory() as db, db.begin():
                            generation = await get(
                                db,
                                scope.company_id,
                                ReportGeneration,
                                identity,
                                lock=True,
                            )
                            if generation.status not in {"PENDING", "BUILDING"}:
                                continue
                            source = await source_request(db, scope.company_id, identity)
                            generation.status, generation.failure_code = (
                                "QUARANTINED",
                                "SOURCE_VERIFICATION_FAILED",
                            )
                            if source.epoch_id:
                                epoch = await get(
                                    db,
                                    scope.company_id,
                                    ReportSourceEpoch,
                                    source.epoch_id,
                                    lock=True,
                                )
                                if epoch.active_generation_id == identity:
                                    epoch.status, epoch.active_generation_id = (
                                        "QUARANTINED",
                                        None,
                                    )
                            audit(
                                db,
                                scope.tenant_id,
                                scope.company_id,
                                identity,
                                "quarantined",
                            )
                    except Exception as exc:
                        logging.getLogger(__name__).warning(
                            "Source worker retry: %s", type(exc).__name__
                        )


async def run(settings: Settings) -> None:
    from reports.tasks.enrollment import owners

    if not settings.source_versions_enabled:
        raise ValueError("versioned source worker is disabled")
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    running: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Task[None]] = {}
    offset = 0
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False, follow_redirects=False) as client:
            while True:
                try:
                    for running_key, task in list(running.items()):
                        if task.done():
                            del running[running_key]
                            try:
                                task.result()
                            except Exception as exc:
                                logging.getLogger(__name__).warning(
                                    "Source company retry: %s", type(exc).__name__
                                )
                    resolved = await owners(settings, client)
                    # Independent bounded tasks: one slow company cannot hold the
                    # next discovery/refresh cycle hostage. Rotate for fairness.
                    start = offset % len(resolved) if resolved else 0
                    for index in range(len(resolved)):
                        if len(running) >= settings.source_parallelism:
                            break
                        position = (start + index) % len(resolved)
                        owner = resolved[position]
                        scope = owner.scopes[0]
                        key = (scope.tenant_id, scope.company_id)
                        if key in running:
                            continue
                        running[key] = asyncio.create_task(
                            cycle(settings.model_copy(update={"owners": (owner,)}), factory, client)
                        )
                        offset = position + 1
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Source discovery retry: %s", type(exc).__name__
                    )
                await asyncio.sleep(2)
    finally:
        for task in running.values():
            task.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    import dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    arguments = parser.parse_args()
    if arguments.env_file:
        dotenv.load_dotenv(arguments.env_file)
    asyncio.run(run(Settings.model_validate({})))
