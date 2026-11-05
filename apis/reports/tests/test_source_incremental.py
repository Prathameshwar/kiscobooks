import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from financial_fixture import financial_manifest
from invoice_fixture import invoice_dataset
from reporting_contract.contract import Fact, digest
from sqlalchemy import select
from test_invoice_reports import _append_credit_note
from test_source_versions import apply_change, change_manifest, staged

from reports.domain.reconcile import reconcile
from reports.models.source_versions import ReportGenerationRequest, ReportSourceCut
from reports.tasks.source_publication import publish
from reports.tasks.source_verification import verify
from tools.framework_data import facts, manifest


async def append_cut(app, *, corrupt=False):
    (epoch, _, generation), proof = await staged(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            parent = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
        await publish(app.state.session_factory, COMPANY, parent.id)
    previous = {(row.entity, row.source_id) for row in facts(10)}
    added = [row for row in facts(11) if (row.entity, row.source_id) not in previous]
    if corrupt:
        index = next(i for i, row in enumerate(added) if row.entity == "journal_line")
        value = added[index].model_dump(mode="json")
        value["data"]["base_amount"] = "999.0000"
        value["content_hash"] = digest({k: v for k, v in value.items() if k != "content_hash"})
        added[index] = Fact.model_validate(value)
    control = manifest(11, tenant=TENANT, company=COMPANY, snapshot=proof.id).control
    changed = change_manifest(proof, added, proof.sequence + 1).model_copy(
        update={"control": control}
    )
    identity = await apply_change(app, epoch, changed, added)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                ReportGenerationRequest(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    generation_id=identity,
                    strategy="REFRESH",
                    parent_cut_id=parent.id,
                    epoch_id=epoch,
                )
            )
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identity)
            )
    return cut, parent, control


async def test_append_verification_matches_full_rebuild_without_rescanning_old_records(
    app, monkeypatch
):
    cut, parent, control = await append_cut(app)

    async def reject_full_scan(*args):
        raise AssertionError("an eligible append must not revisit every old source record")

    monkeypatch.setattr("reports.tasks.source_verification.verify_records", reject_full_scan)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            evidence = await verify(db, cut)
            assert evidence["incremental_from"] == str(parent.id)
            expected = reconcile(list(facts(11)), control)[2]
            assert {key: evidence[key] for key in expected} == expected
        await publish(app.state.session_factory, COMPANY, cut.id)


async def test_changed_existing_metadata_uses_full_verification(app):
    (epoch, _, generation), proof = await staged(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            parent = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
        await publish(app.state.session_factory, COMPANY, parent.id)
    value = next(row for row in facts(10) if row.entity == "account").model_dump(mode="json")
    value["data"]["name"] = "Updated account name"
    value["content_hash"] = digest({k: v for k, v in value.items() if k != "content_hash"})
    rows = [Fact.model_validate(value)]
    changed = change_manifest(proof, rows, proof.sequence + 1)
    identity = await apply_change(app, epoch, changed, rows)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                ReportGenerationRequest(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    generation_id=identity,
                    strategy="REFRESH",
                    parent_cut_id=parent.id,
                    epoch_id=epoch,
                )
            )
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identity)
            )
            assert "incremental_from" not in await verify(db, cut)


async def test_incremental_verification_rejects_unbalanced_new_journal(app):
    cut, _, _ = await append_cut(app, corrupt=True)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            with pytest.raises(ConflictError, match="reconcile"):
                await verify(db, cut)


@pytest.mark.parametrize("prior_amount,amount", [(None, "50"), (None, "201"), ("160", "50")])
async def test_invoice_append_verifies_affected_components_and_global_return_entitlement(
    app, monkeypatch, prior_amount, amount
):
    original, ids = invoice_dataset()
    if prior_amount:
        _append_credit_note(original, ids, prior_amount, "PREVIOUS-CN")
    original.sort(key=lambda row: (row.entity, str(row.source_id)))
    identities, proof = await staged(
        app, source=original, control=financial_manifest(original).control
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            parent = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, parent.id)
    current = list(original)
    _append_credit_note(current, ids, amount, "APPEND-CN")
    previous = {(row.entity, row.source_id) for row in original}
    added = sorted(
        (row for row in current if (row.entity, row.source_id) not in previous),
        key=lambda row: (row.entity, str(row.source_id)),
    )
    control = financial_manifest(current).control
    changed = change_manifest(proof, added, proof.sequence + 1).model_copy(
        update={"control": control}
    )
    identity = await apply_change(app, identities[0], changed, added)

    async def reject_full_scan(*args):
        raise AssertionError(
            "complete new invoice components must not rescan unrelated source history"
        )

    monkeypatch.setattr("reports.tasks.source_verification.verify_records", reject_full_scan)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                ReportGenerationRequest(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    generation_id=identity,
                    strategy="REFRESH",
                    parent_cut_id=parent.id,
                    epoch_id=identities[0],
                )
            )
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identity)
            )
            if amount == "201" or prior_amount:
                with pytest.raises(ConflictError, match="entitlement"):
                    await verify(db, cut)
            else:
                result = await verify(db, cut)
                expected = reconcile(current, control)[2]
                assert {key: result[key] for key in expected} == expected
                assert result["incremental_from"] == str(parent.id)
        if amount == "50" and not prior_amount:
            await publish(app.state.session_factory, COMPANY, cut.id)
