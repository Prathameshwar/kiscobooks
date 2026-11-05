"""Verified source cuts gain immutable claims before a short publication transaction."""

import uuid
from collections import defaultdict

from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.domain.reconcile import immutable_claim
from reports.models.core import ReportActivation, ReportGeneration, ReportSourceClaim
from reports.models.source_versions import ReportSourceCut, ReportSourceEpoch
from reports.queries.projection import QUERY_VERSION
from reports.queries.source_versions import SourceView
from reports.tasks import daily_projection, posted_projection
from reports.tasks.common import audit, company_lock, get
from reports.tasks.source_verification import verify
from reports.tasks.source_versions import fact


async def publish(
    factory: async_sessionmaker[AsyncSession],
    company: uuid.UUID,
    cut_id: uuid.UUID,
) -> None:
    async with factory() as db:
        cut = await get(db, company, ReportSourceCut, cut_id)
        generation = await get(db, company, ReportGeneration, cut.generation_id)
        if generation.status == "READY":
            return
        if generation.status not in {"PENDING", "BUILDING"}:
            raise ConflictError("source generation cannot be published")
        evidence = cut.verification if cut.verification is not None else await verify(db, cut)
        view = SourceView(company, cut.epoch_id, cut.sequence)
        epoch = await get(db, company, ReportSourceEpoch, cut.epoch_id)
        build_native = epoch.query_version == QUERY_VERSION
        expected_posted = 0
        since = None
        base_generation = None
        if evidence.get("incremental_from"):
            parent = await get(
                db, company, ReportSourceCut, uuid.UUID(evidence["incremental_from"])
            )
            activation = await db.scalar(
                select(ReportActivation).where(ReportActivation.company_id == company)
            )
            if activation is not None and activation.generation_id == parent.generation_id:
                since, base_generation = parent.sequence, parent.generation_id
                if build_native:
                    expected_posted = await posted_projection.count(db, cut, since)
    async with factory() as db, db.begin():
        await company_lock(db, cut.tenant_id, company)
        generation = await get(db, company, ReportGeneration, cut.generation_id, lock=True)
        if generation.status == "READY":
            return
        if generation.status not in {"PENDING", "BUILDING"}:
            raise ConflictError("source generation cannot be verified")
        stored = await get(db, company, ReportSourceCut, cut_id, lock=True)
        if stored.verification is None:
            stored.verification = evidence
            audit(db, cut.tenant_id, company, cut_id, "verified")
        elif stored.verification != evidence:
            raise ConflictError("source verification evidence changed")
    # Validate all existing claims before recording new ones. Any deletion is a source failure.
    after = None
    while since is None:
        async with factory() as db:
            query = select(ReportSourceClaim).where(ReportSourceClaim.company_id == company)
            if after is not None:
                query = query.where(ReportSourceClaim.id > after)
            claims = list(await db.scalars(query.order_by(ReportSourceClaim.id).limit(200)))
            grouped: dict[str, list[uuid.UUID]] = defaultdict(list)
            for claim in claims:
                grouped[claim.entity].append(claim.source_id)
            for entity, identities in grouped.items():
                retained = await view.lookup(db, entity, identities)
                if len(retained) != len(identities):
                    raise ConflictError("committed financial source disappeared")
                parent_ids = {
                    uuid.UUID(row.data["journal_id"])
                    for row in retained.values()
                    if entity == "journal_line" and row.data
                }
                parent_journals = {
                    str(key): row.data
                    for key, row in (await view.lookup(db, "journal", parent_ids)).items()
                    if row.data is not None
                }
                expected = {
                    claim.source_id: claim.financial_hash
                    for claim in claims
                    if claim.entity == entity
                }
                for identity, value in retained.items():
                    if immutable_claim(fact(value), parent_journals) != expected[identity]:
                        raise ConflictError("immutable financial source identity changed")
        if len(claims) < 200:
            break
        after = claims[-1].id
    from reporting_contract.contract import FACT_MODELS

    for entity in sorted(FACT_MODELS):
        # Bounded reads and claim writes use separate sessions.
        async with factory() as reader:
            async for rows in view.pages(reader, entity, since=since):
                journal_ids = {
                    uuid.UUID(row.data["journal_id"])
                    for row in rows
                    if entity == "journal_line" and row.data
                }
                journal_versions = await view.lookup(reader, "journal", journal_ids)
                journals = {
                    str(key): row.data
                    for key, row in journal_versions.items()
                    if row.data is not None
                }
                hashes = {
                    (row.entity, row.source_id): immutable_claim(fact(row), journals)
                    for row in rows
                }
                async with factory() as db, db.begin():
                    # Serialize claim comparisons only for this bounded page.
                    await company_lock(db, cut.tenant_id, company)
                    if base_generation is not None:
                        active_generation = await db.scalar(
                            select(ReportActivation.generation_id).where(
                                ReportActivation.company_id == company
                            )
                        )
                        if active_generation not in {base_generation, cut.generation_id}:
                            # A legacy publication raced this refresh; retry with full claim checks.
                            raise RuntimeError(
                                "source activation changed during append publication"
                            )
                    old = {
                        (row.entity, row.source_id): row
                        for row in await db.scalars(
                            select(ReportSourceClaim).where(
                                ReportSourceClaim.company_id == company,
                                tuple_(ReportSourceClaim.entity, ReportSourceClaim.source_id).in_(
                                    list(hashes)
                                ),
                            )
                        )
                    }
                    if build_native and entity == "journal_line":
                        expected_posted += await posted_projection.append(
                            db, cut, rows, journal_versions
                        )
                    for (kind, identity), checksum in hashes.items():
                        previous = old.get((kind, identity))
                        if previous is not None and previous.financial_hash != checksum:
                            raise ConflictError("immutable financial source identity changed")
                        if previous is None and checksum:
                            db.add(
                                ReportSourceClaim(
                                    id=uuid7(),
                                    tenant_id=cut.tenant_id,
                                    company_id=company,
                                    entity=kind,
                                    source_id=identity,
                                    financial_hash=checksum,
                                )
                            )
    if build_native:
        async with factory() as db:
            await posted_projection.verify(db, cut, expected_posted, evidence)
        await daily_projection.build(factory, cut)
        async with factory() as db:
            await daily_projection.verify(db, cut, expected_posted, evidence)
    async with factory() as db, db.begin():
        await company_lock(db, cut.tenant_id, company)
        generation = await get(db, company, ReportGeneration, cut.generation_id, lock=True)
        stored = await get(db, company, ReportSourceCut, cut_id, lock=True)
        epoch = await get(db, company, ReportSourceEpoch, cut.epoch_id, lock=True)
        if generation.status == "READY":
            return
        if generation.status not in {"PENDING", "BUILDING"}:
            raise ConflictError("source generation cannot be published")
        if stored.verification != evidence:
            raise ConflictError("source verification evidence changed")
        generation.status = "READY"
        generation.target_sequence = cut.sequence
        generation.row_version += 1
        if epoch.active_generation_id == generation.id:
            epoch.active_generation_id = None
        active = await db.scalar(
            select(ReportActivation).where(ReportActivation.company_id == company)
        )
        if active is None:
            db.add(
                ReportActivation(
                    tenant_id=cut.tenant_id, company_id=company, generation_id=generation.id
                )
            )
        else:
            if base_generation is not None and active.generation_id not in {
                base_generation,
                generation.id,
            }:
                raise RuntimeError("source activation changed during append publication")
            previous_generation = await get(db, company, ReportGeneration, active.generation_id)
            if previous_generation.applied_sequence <= cut.sequence:
                active.generation_id = generation.id
                active.row_version += 1
        audit(db, cut.tenant_id, company, generation.id, "activated")
