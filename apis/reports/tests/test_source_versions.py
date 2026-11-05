import hashlib
import itertools
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from conftest import COMPANY, TENANT
from reporting_contract.contract import Fact, FactPage, digest
from sqlalchemy import func, select

from reports.models.core import ReportBundle, ReportGeneration
from reports.models.source_versions import (
    VERSION_MODELS,
    ReportFactVersion,
    ReportGenerationRequest,
    ReportSourceEpoch,
)
from reports.queries.source_versions import SourceView, bounded_rows
from reports.tasks import source_versions as versions
from reports.tasks.common import get
from tools.framework_data import facts, manifest


async def staged(app, *, tenant=TENANT, company=COMPANY, source=None, control=None):
    snapshot = uuid.uuid4()
    proof = manifest(10, tenant=tenant, company=company, snapshot=snapshot)
    if control is not None:
        proof = proof.model_copy(update={"control": control})
    values_source = list(facts(10)) if source is None else source
    checksum = hashlib.sha256()
    for value in values_source:
        checksum.update(canonical_json(value.model_dump(mode="json")) + b"\n")
    proof = proof.model_copy(
        update={"fact_count": len(values_source), "facts_hash": checksum.hexdigest()}
    )
    factory = app.state.session_factory
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            generation = ReportGeneration(
                tenant_id=tenant, company_id=company, snapshot_id=snapshot
            )
            db.add(generation)
            await db.flush()
            epoch = await versions.new_epoch(db, generation, proof)
            db.add(
                ReportGenerationRequest(
                    tenant_id=tenant,
                    company_id=company,
                    generation_id=generation.id,
                    strategy="FRESH",
                    epoch_id=epoch.id,
                )
            )
            bundle = await versions.bundle(db, generation, proof)
            identities = epoch.id, bundle.id, generation.id
        after = 0
        for values in itertools.batched(values_source, 17):
            end = after + len(values)
            async with factory() as db, db.begin():
                epoch = await get(db, company, ReportSourceEpoch, identities[0], lock=True)
                bundle = await get(db, company, ReportBundle, identities[1], lock=True)
                page = FactPage(
                    manifest_id=snapshot,
                    items=list(values),
                    next_after=end if end < proof.fact_count else None,
                )
                await versions.stage(db, epoch, bundle, page, after)
                await db.flush()
                await versions.stage(db, epoch, bundle, page, after)
            after = end
        async with factory() as db, db.begin():
            epoch = await get(db, company, ReportSourceEpoch, identities[0], lock=True)
            bundle = await get(db, company, ReportBundle, identities[1], lock=True)
            await versions.finish(db, epoch, bundle)
            await db.flush()
            generation = await get(db, company, ReportGeneration, identities[2])
            await versions.pin(db, epoch, generation, proof)
    return identities, proof


async def test_source_pages_bound_bytes_and_close_cursors_before_nested_reads(app, monkeypatch):
    from reports.queries import source_versions as queries

    identities, proof = await staged(app)
    monkeypatch.setattr(queries, "PAGE_BYTES", 1500)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            view = SourceView(COMPANY, identities[0], proof.sequence)
            found = []
            async for page in view.pages(db, "journal_line"):
                assert sum(queries.fact_bytes(row) for row in page) <= 1500
                ids = [row.source_id for row in page]
                assert set(await view.lookup(db, "journal_line", ids)) == set(ids)
                found.extend(ids)
            assert len(found) == len(set(found)) == 20
            with pytest.raises(ConflictError, match="memory bound"):
                await bounded_rows(db, view.rows("journal_line"), byte_limit=100)
            # A rejected oversized read also releases its cursor for subsequent queries.
            assert len(await view.lookup(db, "journal_line", found)) == 20


@pytest.mark.parametrize("field", ["relation_id", "account_id", "base_amount", "source_status"])
async def test_source_native_projection_cannot_disagree_with_retained_payload(app, field):
    from decimal import Decimal

    identities, proof = await staged(app)
    fact = next(value for value in facts(10) if value.entity == "journal_line")
    values = versions.projection(fact)
    values[field] = (
        Decimal("999.0000")
        if field == "base_amount"
        else "CORRUPTED"
        if field == "source_status"
        else uuid.uuid4()
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                ReportFactVersion(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    epoch_id=identities[0],
                    bundle_id=identities[1],
                    ordinal=proof.fact_count + 1,
                    entity=fact.entity,
                    source_id=uuid.uuid4(),
                    valid_from_sequence=proof.sequence + 1,
                    content_hash=fact.content_hash,
                    data=fact.data,
                    **values,
                )
            )
            with pytest.raises(ConflictError, match="projection"):
                await db.flush()
            await db.rollback()


def change_manifest(proof, values, sequence):
    checksum = hashlib.sha256()
    for value in values:
        checksum.update(canonical_json(value.model_dump(mode="json")) + b"\n")
    return proof.model_copy(
        update={
            "id": uuid.uuid4(),
            "kind": "CHANGE",
            "sequence": sequence,
            "fact_count": len(values),
            "facts_hash": checksum.hexdigest(),
        }
    )


async def apply_change(app, epoch_id, proof, values):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            epoch = await get(db, COMPANY, ReportSourceEpoch, epoch_id, lock=True)
            generation = ReportGeneration(
                tenant_id=TENANT, company_id=COMPANY, snapshot_id=epoch.snapshot_id
            )
            db.add(generation)
            await db.flush()
            bundle = await versions.bundle(db, generation, proof)
            await versions.stage(db, epoch, bundle, FactPage(manifest_id=proof.id, items=values), 0)
            await versions.finish(db, epoch, bundle)
            await versions.pin(db, epoch, generation, proof)
            return generation.id


async def test_source_cut_retains_old_values_across_update_delete_and_restore(app):
    (epoch_id, _, _), proof = await staged(app)
    original = next(row for row in facts(10) if row.entity == "account")
    revised = original.model_dump(mode="json")
    revised["data"] = revised["data"] | {"name": "New classification name"}
    revised["content_hash"] = digest(
        {key: value for key, value in revised.items() if key != "content_hash"}
    )
    updated = Fact.model_validate(revised)
    await apply_change(
        app, epoch_id, change_manifest(proof, [updated], proof.sequence + 1), [updated]
    )
    # Interval storage is independent from the later financial reconciliation gate.
    deleted = {"entity": original.entity, "source_id": str(original.source_id), "data": None}
    tombstone = Fact.model_validate(deleted | {"content_hash": digest(deleted)})
    await apply_change(
        app, epoch_id, change_manifest(proof, [tombstone], proof.sequence + 2), [tombstone]
    )
    await apply_change(
        app, epoch_id, change_manifest(proof, [original], proof.sequence + 3), [original]
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for offset, expected in (
                (0, original.data),
                (1, updated.data),
                (2, None),
                (3, original.data),
            ):
                view = SourceView(COMPANY, epoch_id, proof.sequence + offset)
                result = await view.lookup(db, "account", [original.source_id])
                assert (result[original.source_id].data if result else None) == expected
            assert await db.scalar(select(func.count(ReportFactVersion.id))) == proof.fact_count + 3
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                row = await db.scalar(
                    select(ReportFactVersion)
                    .where(ReportFactVersion.source_id == original.source_id)
                    .order_by(ReportFactVersion.valid_from_sequence)
                    .limit(1)
                )
                row.valid_to_sequence += 1


async def test_version_tables_are_tenant_scoped_and_financial_payloads_are_frozen(app):
    (epoch_id, _, _), proof = await staged(app)
    line = next(row for row in facts(10) if row.entity == "journal_line")
    changed = line.model_dump(mode="json")
    changed["data"] = changed["data"] | {"base_amount": "999.0000"}
    changed["content_hash"] = digest(
        {key: value for key, value in changed.items() if key != "content_hash"}
    )
    changed = Fact.model_validate(changed)
    with pytest.raises(ConflictError, match="committed source identity"):
        await apply_change(
            app, epoch_id, change_manifest(proof, [changed], proof.sequence + 1), [changed]
        )
    other = uuid.uuid4()
    with tenant_scope(other):
        async with app.state.session_factory() as db:
            for model in VERSION_MODELS:
                assert await db.scalar(select(func.count(model.id))) == 0
    await staged(app, tenant=other)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportFactVersion.id))) == proof.fact_count
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                row = await db.scalar(select(ReportFactVersion).limit(1))
                row.content_hash = "f" * 64


@pytest.mark.parametrize("target", ["interval", "verification", "epoch", "request"])
async def test_retained_source_evidence_cannot_be_rewritten_after_attribute_expiry(app, target):
    from reports.models.source_versions import ReportSourceCut

    (epoch_id, _, generation), proof = await staged(app)
    original = next(row for row in facts(10) if row.entity == "account")
    value = original.model_dump(mode="json")
    value["data"]["name"] = "New classification"
    value["content_hash"] = digest(
        {key: item for key, item in value.items() if key != "content_hash"}
    )
    changed = Fact.model_validate(value)
    await apply_change(app, epoch_id, change_manifest(proof, [changed], 2), [changed])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
            cut.verification = {"retained": "original"}
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                if target == "interval":
                    row = await db.scalar(
                        select(ReportFactVersion).where(
                            ReportFactVersion.source_id == original.source_id,
                            ReportFactVersion.valid_from_sequence == proof.sequence,
                        )
                    )
                    db.expire(row, ["valid_to_sequence"])
                    row.valid_to_sequence = 3
                elif target == "verification":
                    row = await db.scalar(
                        select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
                    )
                    db.expire(row, ["verification"])
                    row.verification = {"retained": "replaced"}
                elif target == "epoch":
                    row = await db.get(ReportSourceEpoch, epoch_id)
                    db.expire(row, ["head_sequence"])
                    row.head_sequence = 0
                else:
                    row = await db.scalar(
                        select(ReportGenerationRequest).where(
                            ReportGenerationRequest.generation_id == generation
                        )
                    )
                    db.expire(row, ["epoch_id"])
                    row.epoch_id = None
