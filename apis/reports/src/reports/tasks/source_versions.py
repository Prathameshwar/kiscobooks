"""Incremental append/close batches; publication advances only a verified owner bundle."""

import hashlib
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from reporting_contract.contract import Fact, FactPage, Manifest
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reconcile import immutable_claim
from reports.models.core import ReportBundle, ReportGeneration
from reports.models.source_versions import ReportFactVersion, ReportSourceCut, ReportSourceEpoch
from reports.queries.projection import QUERY_VERSION, source_projection
from reports.queries.source_versions import SourceView, bounded_rows, fact_pages
from reports.tasks.common import audit, get


def projection(item: Fact) -> dict[str, Any]:
    return source_projection(item.entity, item.data)


async def new_epoch(
    db: AsyncSession, generation: ReportGeneration, manifest: Manifest
) -> ReportSourceEpoch:
    if manifest.kind != "SNAPSHOT" or (
        generation.tenant_id,
        generation.company_id,
        generation.snapshot_id,
    ) != (manifest.tenant_id, manifest.company_id, manifest.id):
        raise ConflictError("base snapshot identity differs")
    row = ReportSourceEpoch(
        tenant_id=generation.tenant_id,
        company_id=generation.company_id,
        head_sequence=manifest.sequence,
        snapshot_id=manifest.id,
        owner_generation=manifest.generation,
        schema_hash=manifest.schema_hash,
        scope_hash=manifest.scope_hash,
        permission_hash=manifest.permission_hash,
        query_version=QUERY_VERSION,
    )
    db.add(row)
    await db.flush()
    return row


async def bundle(
    db: AsyncSession, generation: ReportGeneration, manifest: Manifest
) -> ReportBundle:
    if (generation.tenant_id, generation.company_id) != (manifest.tenant_id, manifest.company_id):
        raise ConflictError("source manifest scope differs")
    if generation.status not in {"PENDING", "BUILDING"}:
        raise ConflictError("generation is frozen")
    prior = await db.scalar(
        select(ReportBundle).where(
            ReportBundle.company_id == generation.company_id,
            ReportBundle.generation_id == generation.id,
            ReportBundle.source_id == manifest.id,
        )
    )
    if prior is not None:
        if prior.manifest != manifest.model_dump(mode="json"):
            raise ConflictError("source manifest identity changed")
        return prior
    row = ReportBundle(
        tenant_id=generation.tenant_id,
        company_id=generation.company_id,
        generation_id=generation.id,
        source_id=manifest.id,
        manifest=manifest.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    return row


async def stage(
    db: AsyncSession,
    epoch: ReportSourceEpoch,
    bundle: ReportBundle,
    page: FactPage,
    after: int,
) -> None:
    manifest = Manifest.model_validate(bundle.manifest)
    if manifest.permission_hash != epoch.permission_hash:
        raise ConflictError("source permission scope changed")
    if (
        epoch.company_id,
        epoch.tenant_id,
        manifest.generation,
        manifest.schema_hash,
        manifest.scope_hash,
    ) != (
        bundle.company_id,
        manifest.tenant_id,
        epoch.owner_generation,
        epoch.schema_hash,
        epoch.scope_hash,
    ):
        raise ConflictError("source epoch contract differs")
    if manifest.kind == "CHANGE" and manifest.sequence != epoch.head_sequence + 1:
        if bundle.status == "APPLIED" and after + len(page.items) <= bundle.last_ordinal:
            pass  # Compare replay content below; never rewrite old intervals.
        else:
            raise ConflictError("incremental source sequence is incomplete")
    if manifest.kind == "SNAPSHOT" and (
        manifest.id != epoch.snapshot_id or manifest.sequence != epoch.head_sequence
    ):
        raise ConflictError("snapshot does not belong to this epoch")
    end = after + len(page.items)
    if (
        page.manifest_id != manifest.id
        or after < 0
        or end > manifest.fact_count
        or (page.next_after is None and end != manifest.fact_count)
        or (page.next_after is not None and page.next_after != end)
        or (not page.items and end != manifest.fact_count)
    ):
        raise ConflictError("source page boundary differs")
    if after != bundle.last_ordinal or bundle.status == "APPLIED":
        if end > bundle.last_ordinal:
            raise ConflictError("source page leaves a gap")
        prior = list(
            await db.scalars(
                select(ReportFactVersion)
                .where(
                    ReportFactVersion.company_id == epoch.company_id,
                    ReportFactVersion.bundle_id == bundle.id,
                    ReportFactVersion.ordinal > after,
                    ReportFactVersion.ordinal <= end,
                )
                .order_by(ReportFactVersion.ordinal)
            )
        )
        if [fact(row).model_dump(mode="json") for row in prior] != [
            item.model_dump(mode="json") for item in page.items
        ]:
            raise ConflictError("replayed source content differs")
        return
    keys = [(item.entity, item.source_id) for item in page.items]
    if len(set(keys)) != len(keys):
        raise ConflictError("source bundle repeats an identity")
    # The same identity is forbidden even when repeated across separate pages.
    repeated = (
        await db.scalar(
            select(ReportFactVersion.id)
            .where(
                ReportFactVersion.company_id == epoch.company_id,
                ReportFactVersion.epoch_id == epoch.id,
                ReportFactVersion.bundle_id == bundle.id,
                tuple_(ReportFactVersion.entity, ReportFactVersion.source_id).in_(keys),
            )
            .limit(1)
        )
        if keys
        else None
    )
    if repeated is not None:
        raise ConflictError("source bundle repeats an identity")
    previous = {}
    if manifest.kind == "CHANGE" and keys:
        view = SourceView(epoch.company_id, epoch.id, epoch.head_sequence)
        previous = {
            (row.entity, row.source_id): row
            for row in await bounded_rows(
                db,
                select(ReportFactVersion).where(
                    view.predicate(live=False),
                    tuple_(ReportFactVersion.entity, ReportFactVersion.source_id).in_(keys),
                ),
            )
        }
        # One lookup for this page's old journals, never one query per line.
        journal_ids = {
            uuid.UUID(row.data["journal_id"])
            for row in previous.values()
            if row.entity == "journal_line" and row.data
        }
        journals = {
            str(key): value.data
            for key, value in (await view.lookup(db, "journal", journal_ids)).items()
            if value.data is not None
        }
    else:
        journals = {}
    for ordinal, item in enumerate(page.items, after + 1):
        old = previous.get((item.entity, item.source_id))
        if old is not None:
            claim = immutable_claim(fact(old), journals)
            if claim and (item.data is None or immutable_claim(item, journals) != claim):
                raise ConflictError("committed source identity changed")
            old.valid_to_sequence = manifest.sequence
        db.add(
            ReportFactVersion(
                id=uuid7(),
                tenant_id=epoch.tenant_id,
                company_id=epoch.company_id,
                epoch_id=epoch.id,
                bundle_id=bundle.id,
                ordinal=ordinal,
                entity=item.entity,
                source_id=item.source_id,
                valid_from_sequence=manifest.sequence,
                data=item.data,
                content_hash=item.content_hash,
                **projection(item),
            )
        )
    # Interval guard observes the previously published head, before any checkpoint advance.
    await db.flush()
    bundle.last_ordinal = end


def fact(row: ReportFactVersion) -> Fact:
    return Fact(
        entity=row.entity, source_id=row.source_id, data=row.data, content_hash=row.content_hash
    )


async def finish(db: AsyncSession, epoch: ReportSourceEpoch, bundle: ReportBundle) -> None:
    if bundle.status == "APPLIED":
        return
    manifest = Manifest.model_validate(bundle.manifest)
    if bundle.last_ordinal != manifest.fact_count:
        raise ConflictError("source bundle has not reached its terminal boundary")
    checksum, after = hashlib.sha256(), 0
    query = select(ReportFactVersion).where(
        ReportFactVersion.company_id == epoch.company_id,
        ReportFactVersion.epoch_id == epoch.id,
        ReportFactVersion.bundle_id == bundle.id,
    )
    async for rows in fact_pages(db, query, key="ordinal"):
        for row in rows:
            if row.ordinal != after + 1:
                raise ConflictError("source bundle ordinal differs")
            checksum.update(canonical_json(fact(row).model_dump(mode="json")) + b"\n")
            after += 1
    if after != manifest.fact_count or checksum.hexdigest() != manifest.facts_hash:
        raise ConflictError("source bundle checksum differs")
    epoch.head_sequence, epoch.status = manifest.sequence, "READY"
    epoch.row_version += 1
    bundle.status = "APPLIED"
    generation = await get(db, epoch.company_id, ReportGeneration, bundle.generation_id, lock=True)
    generation.manifest = manifest.model_dump(mode="json")
    generation.applied_sequence = manifest.sequence
    generation.status = "BUILDING"
    audit(db, epoch.tenant_id, epoch.company_id, bundle.id, "ingested")


async def pin(
    db: AsyncSession, epoch: ReportSourceEpoch, generation: ReportGeneration, manifest: Manifest
) -> ReportSourceCut:
    if epoch.status != "READY" or epoch.head_sequence != manifest.sequence:
        raise ConflictError("source epoch has not reached the requested cut")
    cut = ReportSourceCut(
        tenant_id=epoch.tenant_id,
        company_id=epoch.company_id,
        epoch_id=epoch.id,
        generation_id=generation.id,
        sequence=manifest.sequence,
        manifest=manifest.model_dump(mode="json"),
    )
    db.add(cut)
    await db.flush()
    return cut
