import pytest
from bank_evidence_fixture import evidence_dataset
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from financial_fixture import financial_dataset, financial_manifest
from invoice_fixture import invoice_dataset
from reporting_contract.contract import Fact, digest
from sqlalchemy import select
from test_invoice_reports import _append_credit_note
from test_source_versions import staged

from reports.domain.reconcile import reconcile
from reports.models.source_versions import ReportSourceCut
from reports.tasks.source_verification import verify
from tools.framework_data import facts


@pytest.mark.parametrize("family", ["statements", "invoice", "bank"])
async def test_versioned_verification_covers_all_source_families(app, family):
    source = (
        invoice_dataset()[0]
        if family == "invoice"
        else evidence_dataset()[0]
        if family == "bank"
        else financial_dataset()[0]
    )
    control = financial_manifest(source).control
    (_, _, generation), _ = await staged(app, source=source, control=control)
    expected = reconcile(source, control)[2]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
            assert await verify(db, cut) == expected | {"projection_version": 1}


async def test_streamed_verification_matches_reference_controls(app):
    (_, _, generation), proof = await staged(app)
    expected = reconcile(list(facts(10)), proof.control)[2]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
            actual = await verify(db, cut)
            assert actual == expected | {"projection_version": 1}


@pytest.mark.parametrize("notes", [10, 11])
async def test_cumulative_note_entitlement_is_checked_across_component_batches(app, notes):
    source, identities = invoice_dataset()
    for index in range(notes):
        _append_credit_note(source, identities, "19", f"CN-{index}")
    control = financial_manifest(source).control
    (_, _, generation), _ = await staged(app, source=source, control=control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
            if notes == 10:
                assert (await verify(db, cut))["differences"] == []
            else:
                with pytest.raises(ConflictError, match="entitlement"):
                    await verify(db, cut)


@pytest.mark.parametrize(
    "failure", ["missing_reference", "unbalanced", "grain_count", "header_total"]
)
async def test_source_verification_rejects_complete_but_inconsistent_owner_data(app, failure):
    source = list(facts(10))
    if failure == "grain_count":
        source = source[1:]
    else:
        index = next(
            index
            for index, row in enumerate(source)
            if row.entity == ("journal" if failure == "header_total" else "journal_line")
        )
        value = source[index].model_dump(mode="json")
        field, replacement = {
            "missing_reference": ("account_id", str(COMPANY)),
            "unbalanced": ("base_amount", "321.0000"),
            "header_total": ("total_debit", "321.0000"),
        }[failure]
        value["data"] = value["data"] | {field: replacement}
        value["content_hash"] = digest(
            {key: data for key, data in value.items() if key != "content_hash"}
        )
        source[index] = Fact.model_validate(value)
    (_, _, generation), _ = await staged(app, source=source)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == generation)
            )
            with pytest.raises(ConflictError):
                await verify(db, cut)
