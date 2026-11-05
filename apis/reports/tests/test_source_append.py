import hashlib
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from conftest import COMPANY, TENANT
from reporting_contract.contract import FactPage
from sqlalchemy import func, select
from test_source_versions import staged

from reports.models.core import ReportBundle, ReportGeneration
from reports.models.source_versions import ReportFactVersion, ReportSourceEpoch
from reports.queries.source_versions import SourceView
from reports.tasks.source_append import append_window
from tools.framework_freshness import Feed


async def prepared(app):
    feed = Feed(TENANT, COMPANY)
    identities, proof = await staged(app, source=feed.initial, control=feed.base.control)
    feed.produce(3, 100)
    incoming = [
        (
            feed.proofs[index],
            FactPage(
                manifest_id=feed.proofs[index].id,
                items=feed.values[str(feed.proofs[index].id)],
                next_after=None,
            ),
        )
        for index in range(2, 5)
    ]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            generation = ReportGeneration(
                tenant_id=TENANT,
                company_id=COMPANY,
                snapshot_id=uuid.uuid4(),
                status="BUILDING",
                manifest=proof.model_dump(mode="json"),
                applied_sequence=1,
                target_sequence=4,
            )
            db.add(generation)
            await db.flush()
            epoch = await db.get(ReportSourceEpoch, identities[0])
            epoch.active_generation_id = generation.id
    return identities[0], generation.id, incoming


async def test_complete_append_window_is_atomic_preserves_old_cuts_and_audited(app):
    epoch_id, generation_id, incoming = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            epoch = await db.get(ReportSourceEpoch, epoch_id)
            generation = await db.get(ReportGeneration, generation_id)
            assert await append_window(db, generation, epoch, incoming)
        async with app.state.session_factory() as db:
            assert (await db.get(ReportGeneration, generation_id)).applied_sequence == 4
            old = SourceView(COMPANY, epoch_id, 1)
            latest = SourceView(COMPANY, epoch_id, 4)
            query = select(func.count(ReportFactVersion.id)).where(
                ReportFactVersion.entity == "journal_line"
            )
            assert await db.scalar(query.where(old.predicate())) == 2
            assert await db.scalar(query.where(latest.predicate())) == 8
            assert (
                await db.scalar(
                    select(func.count(ReportBundle.id)).where(
                        ReportBundle.generation_id == generation_id,
                        ReportBundle.status == "APPLIED",
                    )
                )
                == 3
            )


@pytest.mark.parametrize("fault", ["hash", "sequence", "scope", "page", "fence", "permission"])
async def test_invalid_append_window_cannot_advance_or_write_any_fact(app, fault):
    epoch_id, generation_id, incoming = await prepared(app)
    manifest, page = incoming[-1]
    updates = {
        "hash": {"facts_hash": "0" * 64},
        "sequence": {"sequence": 7},
        "scope": {"company_id": uuid.uuid4()},
        "permission": {"permission_hash": "0" * 64},
    }
    if fault in updates:
        incoming[-1] = manifest.model_copy(update=updates[fault]), page
    elif fault == "page":
        incoming[-1] = manifest, page.model_copy(update={"manifest_id": uuid.uuid4()})
    with tenant_scope(TENANT):
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                epoch = await db.get(ReportSourceEpoch, epoch_id)
                generation = await db.get(ReportGeneration, generation_id)
                if fault == "fence":
                    epoch.active_generation_id = None
                await append_window(db, generation, epoch, incoming)
        async with app.state.session_factory() as db:
            assert (await db.get(ReportSourceEpoch, epoch_id)).head_sequence == 1
            assert (
                await db.scalar(
                    select(func.count(ReportBundle.id)).where(
                        ReportBundle.generation_id == generation_id
                    )
                )
                == 0
            )


@pytest.mark.parametrize("kind", ["repeated", "existing", "partial", "tombstone"])
async def test_append_falls_back_without_writes_for_interval_or_partial_bundles(app, kind):
    epoch_id, generation_id, incoming = await prepared(app)
    proof, page = incoming[-1]
    items = list(page.items)
    if kind == "partial":
        page = page.model_copy(update={"next_after": len(items)})
    else:
        item = items[0]
        if kind == "tombstone":
            items[0] = item.model_copy(update={"data": None})
        else:
            prior = incoming[0][1].items[0] if kind == "repeated" else Feed(TENANT, COMPANY).journal
            items[0] = prior
        page = page.model_copy(update={"items": items})
        proof = proof.model_copy(
            update={
                "facts_hash": hashlib.sha256(
                    b"".join(canonical_json(item.model_dump(mode="json")) + b"\n" for item in items)
                ).hexdigest()
            }
        )
    incoming[-1] = proof, page
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            epoch = await db.get(ReportSourceEpoch, epoch_id)
            generation = await db.get(ReportGeneration, generation_id)
            assert not await append_window(db, generation, epoch, incoming)
            assert epoch.head_sequence == 1
            assert (
                await db.scalar(
                    select(func.count(ReportBundle.id)).where(
                        ReportBundle.generation_id == generation_id
                    )
                )
                == 0
            )
