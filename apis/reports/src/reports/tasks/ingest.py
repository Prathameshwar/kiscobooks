"""Stage bounded pages; publish only complete, reconciled immutable generations."""

import hashlib
import uuid

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from reporting_contract.contract import Fact, FactPage, Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reconcile import immutable_claim, reconcile
from reports.models import core as m
from reports.tasks.common import audit, get


async def bundle(
    db: AsyncSession, generation: m.ReportGeneration, manifest: Manifest
) -> m.ReportBundle:
    if (manifest.tenant_id, manifest.company_id) != (generation.tenant_id, generation.company_id):
        raise ConflictError("source manifest scope differs")
    prior = await db.scalar(
        select(m.ReportBundle).where(
            m.ReportBundle.company_id == generation.company_id,
            m.ReportBundle.generation_id == generation.id,
            m.ReportBundle.source_id == manifest.id,
        )
    )
    if prior:
        if prior.manifest != manifest.model_dump(mode="json"):
            raise ConflictError("source manifest identity changed")
        return prior
    if generation.status not in {"PENDING", "BUILDING"}:
        raise ConflictError("generation is frozen")
    if manifest.kind == "SNAPSHOT":
        if generation.snapshot_id != manifest.id or generation.manifest is not None:
            raise ConflictError("snapshot identity differs")
    elif manifest.sequence != generation.applied_sequence + 1 or generation.manifest is None:
        raise ConflictError("source sequence is incomplete")
    row = m.ReportBundle(
        tenant_id=generation.tenant_id,
        company_id=generation.company_id,
        generation_id=generation.id,
        source_id=manifest.id,
        manifest=manifest.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    return row


async def stage(db: AsyncSession, row: m.ReportBundle, page: FactPage, after: int) -> None:
    expected = Manifest.model_validate(row.manifest)
    if page.manifest_id != row.source_id or after < 0:
        raise ConflictError("source page identity differs")
    end = after + len(page.items)
    if end > expected.fact_count or (page.next_after is not None and page.next_after != end):
        raise ConflictError("source page boundary differs")
    if page.next_after is None and end != expected.fact_count:
        raise ConflictError("source ended before its barrier")
    if not page.items and end != expected.fact_count:
        raise ConflictError("source page made no progress")
    if after != row.last_ordinal:
        if end > row.last_ordinal:
            raise ConflictError("source pages are out of order")
        old = list(
            await db.scalars(
                select(m.ReportStagedFact)
                .where(
                    m.ReportStagedFact.company_id == row.company_id,
                    m.ReportStagedFact.bundle_id == row.id,
                    m.ReportStagedFact.ordinal > after,
                    m.ReportStagedFact.ordinal <= end,
                )
                .order_by(m.ReportStagedFact.ordinal)
            )
        )
        if [item.fact for item in old] != [item.model_dump(mode="json") for item in page.items]:
            raise ConflictError("duplicate source page changed")
        return
    if row.status != "STAGING":
        raise ConflictError("source bundle is already applied")
    for ordinal, item in enumerate(page.items, after + 1):
        db.add(
            m.ReportStagedFact(
                tenant_id=row.tenant_id,
                company_id=row.company_id,
                bundle_id=row.id,
                ordinal=ordinal,
                fact=item.model_dump(mode="json"),
            )
        )
    row.last_ordinal = end


async def staged(db: AsyncSession, row: m.ReportBundle) -> list[Fact]:
    records = list(
        await db.scalars(
            select(m.ReportStagedFact)
            .where(
                m.ReportStagedFact.company_id == row.company_id,
                m.ReportStagedFact.bundle_id == row.id,
            )
            .order_by(m.ReportStagedFact.ordinal)
            .limit(100001)
        )
    )
    if len(records) > 100000:
        raise ConflictError("source bundle exceeds supported bound")
    checksum = hashlib.sha256()
    values = []
    for record in records:
        checksum.update(canonical_json(record.fact) + b"\n")
        values.append(Fact.model_validate(record.fact))
    manifest = Manifest.model_validate(row.manifest)
    if len(records) != manifest.fact_count or checksum.hexdigest() != manifest.facts_hash:
        raise ConflictError("source bundle checksum or count differs")
    if len({(item.entity, item.source_id) for item in values}) != len(values):
        raise ConflictError("source bundle repeats an identity")
    return values


async def apply(db: AsyncSession, generation: m.ReportGeneration, row: m.ReportBundle) -> None:
    if row.status == "APPLIED":
        return
    manifest = Manifest.model_validate(row.manifest)
    if generation.status not in {"PENDING", "BUILDING"}:
        raise ConflictError("generation is frozen")
    if manifest.kind == "CHANGE" and manifest.sequence != generation.applied_sequence + 1:
        raise ConflictError("source sequence is incomplete")
    items = await staged(db, row)
    if manifest.kind == "CHANGE" and (
        generation.manifest is None
        or manifest.scope_hash != generation.manifest["scope_hash"]
        or manifest.permission_hash != generation.manifest["permission_hash"]
    ):
        raise ConflictError("source scope changed during catch-up")
    prior_journals = {
        str(journal_row.source_id): journal_row.data
        for journal_row in await db.scalars(
            select(m.ReportFact)
            .where(
                m.ReportFact.company_id == row.company_id,
                m.ReportFact.generation_id == generation.id,
                m.ReportFact.entity == "journal",
            )
            .limit(100001)
        )
        if journal_row.data is not None
    }
    for item in items:
        old = await db.scalar(
            select(m.ReportFact).where(
                m.ReportFact.company_id == row.company_id,
                m.ReportFact.generation_id == generation.id,
                m.ReportFact.entity == item.entity,
                m.ReportFact.source_id == item.source_id,
            )
        )
        if old is not None:
            previous_fact = Fact(
                entity=old.entity,
                source_id=old.source_id,
                data=old.data,
                content_hash=old.content_hash,
            )
            previous_claim = immutable_claim(previous_fact, prior_journals)
            if previous_claim and (
                item.data is None or immutable_claim(item, prior_journals) != previous_claim
            ):
                raise ConflictError("committed source content changed during catch-up")
        if old is None:
            db.add(
                m.ReportFact(
                    tenant_id=row.tenant_id,
                    company_id=row.company_id,
                    generation_id=generation.id,
                    entity=item.entity,
                    source_id=item.source_id,
                    content_hash=item.content_hash,
                    data=item.data,
                )
            )
        else:
            old.content_hash = item.content_hash
            old.data = item.data
    generation.applied_sequence = manifest.sequence
    generation.manifest = manifest.model_dump(mode="json")
    generation.status = "BUILDING"
    row.status = "APPLIED"
    audit(db, row.tenant_id, row.company_id, row.id, "ingested")


async def current_facts(db: AsyncSession, generation: m.ReportGeneration) -> list[Fact]:
    rows = list(
        await db.scalars(
            select(m.ReportFact)
            .where(
                m.ReportFact.company_id == generation.company_id,
                m.ReportFact.generation_id == generation.id,
            )
            .order_by(m.ReportFact.entity, m.ReportFact.source_id)
            .limit(100001)
        )
    )
    if len(rows) > 100000:
        raise ConflictError("generation exceeds supported source bound")
    return [
        Fact(
            entity=row.entity, source_id=row.source_id, data=row.data, content_hash=row.content_hash
        )
        for row in rows
    ]


async def activate(db: AsyncSession, generation: m.ReportGeneration) -> None:
    if generation.status == "READY":
        return
    if (
        generation.status != "BUILDING"
        or generation.manifest is None
        or generation.target_sequence != generation.applied_sequence
    ):
        raise ConflictError("generation has not reached the committed barrier")
    manifest = Manifest.model_validate(generation.manifest)
    facts = await current_facts(db, generation)
    lines, totals, evidence = reconcile(facts, manifest.control)
    journals = {
        str(item.source_id): item.data
        for item in facts
        if item.entity == "journal" and item.data is not None
    }
    old_claims = list(
        await db.scalars(
            select(m.ReportSourceClaim)
            .where(m.ReportSourceClaim.company_id == generation.company_id)
            .limit(100001)
        )
    )
    live_ids = {(item.entity, item.source_id) for item in facts if item.data is not None}
    if len(old_claims) > 100000 or any(
        (claim.entity, claim.source_id) not in live_ids for claim in old_claims
    ):
        raise ConflictError("committed financial source disappeared from the owner export")
    for item in facts:
        financial_hash = immutable_claim(item, journals)
        old = await db.scalar(
            select(m.ReportSourceClaim).where(
                m.ReportSourceClaim.company_id == generation.company_id,
                m.ReportSourceClaim.entity == item.entity,
                m.ReportSourceClaim.source_id == item.source_id,
            )
        )
        if old and (item.data is None or financial_hash != old.financial_hash):
            raise ConflictError("immutable financial source identity changed")
        if financial_hash and old is None:
            db.add(
                m.ReportSourceClaim(
                    tenant_id=generation.tenant_id,
                    company_id=generation.company_id,
                    entity=item.entity,
                    source_id=item.source_id,
                    financial_hash=financial_hash,
                )
            )
    values = {
        "tenant_id": generation.tenant_id,
        "company_id": generation.company_id,
        "generation_id": generation.id,
    }
    for line in lines:
        db.add(
            m.ReportLine(
                **values,
                **{
                    key: uuid.UUID(value) if key.endswith("_id") and value else value
                    for key, value in line.items()
                },
            )
        )
    for total in totals:
        db.add(
            m.ReportAccountTotal(
                **values, **(total | {"account_id": uuid.UUID(total["account_id"])})
            )
        )
    active = await db.scalar(
        select(m.ReportActivation).where(m.ReportActivation.company_id == generation.company_id)
    )
    if active:
        previous = await get(db, generation.company_id, m.ReportGeneration, active.generation_id)
        if previous.applied_sequence > generation.applied_sequence:
            raise ConflictError("a newer generation is already active")
        active.generation_id = generation.id
        active.row_version += 1
    else:
        db.add(
            m.ReportActivation(
                tenant_id=generation.tenant_id,
                company_id=generation.company_id,
                generation_id=generation.id,
            )
        )
    generation.status = "READY"
    generation.row_version += 1
    audit(db, generation.tenant_id, generation.company_id, generation.id, "activated")
