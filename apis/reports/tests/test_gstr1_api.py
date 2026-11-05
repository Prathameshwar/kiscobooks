import uuid

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from financial_fixture import financial_dataset, financial_manifest
from fixtures import source
from sqlalchemy import select
from test_framework_execution import proof
from test_gstr1_calculation import REG, amendment, coverage, document
from test_gstr3b_api import GST
from test_source_versions import staged

from reports.models.source_versions import ReportSourceCut
from reports.tasks.framework_worker import process
from reports.tasks.source_publication import publish

REGISTRATION = REG["id"]
GSTR1_GST = (GST[0] | {"id": REGISTRATION, "outward_profiles": REG["outward_profiles"]},)
BASE = f"/v2/companies/{COMPANY}"


async def prepared(app, client, *, ready=True, outward=None):
    facts, _ = financial_dataset()
    records = (
        outward
        if outward is not None
        else coverage([document()], sequence=1)
        if ready
        else [document()]
    )
    facts.extend(
        source(
            "gst_outward_record",
            uuid.UUID(row["id"]),
            {key: value for key, value in row.items() if key != "id"},
        )
        for row in records
    )
    facts.sort(key=lambda row: (row.entity, str(row.source_id)))
    identities, _ = await staged(app, source=facts, control=financial_manifest(facts).control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    response = await client.post(
        BASE + "/report-runs",
        headers=headers(registrations=GSTR1_GST),
        json={
            "code": "GSTR1",
            "generation_id": str(identities[2]),
            "parameters": {"registration_id": REGISTRATION, "period": "2026-10"},
        },
    )
    assert response.status_code == 202, response.text

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(response.json()["id"]),
        authority,
    )
    result = await client.get(
        BASE + "/report-runs/" + response.json()["id"], headers=headers(registrations=GSTR1_GST)
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "COMPLETE", result.text
    return response.json()["id"], result.json()


async def test_gstr1_frozen_tables_search_and_immutable_review_without_3b_payments(app, client):
    identity, value = await prepared(app, client)
    evidence = value["result"]["evidence"]["gstr1"]
    assert evidence["issues"] == [], evidence["issues"]
    assert evidence["bridge"]["3.1a"]["igst"] == "180.00"
    auth = headers(registrations=GSTR1_GST, permissions=PERMISSIONS | {"accounting.finance.manage"})
    page = await client.get(
        BASE + f"/report-runs/{identity}/gstr1-records?category=4A&q=INV-1", headers=auth
    )
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["data"]["recipient_gstin"] == "24ABCDE1234F1Z5"
    review = await client.post(
        BASE + f"/report-runs/{identity}/gstr1-review",
        headers=auth,
        json={"state": "REVIEWED", "reference": "Internal proof", "evidence_hash": "a" * 64},
    )
    assert review.status_code == 201, review.text
    filed = await client.post(
        BASE + f"/report-runs/{identity}/gstr1-review",
        headers=auth,
        json={
            "state": "EXTERNALLY_FILED",
            "reference": "Actual test acknowledgement",
            "evidence_hash": "b" * 64,
            "filed_date": "2026-11-01",
        },
    )
    assert filed.status_code == 201, filed.text
    blocked = await client.post(
        BASE + "/report-runs",
        headers=auth,
        json={
            "code": "GSTR1",
            "generation_id": value["generation_id"],
            "parameters": {"registration_id": REGISTRATION, "period": "2026-10"},
        },
    )
    assert blocked.status_code == 409, blocked.text


async def test_missing_sources_cannot_be_marked_reviewed_and_non_india_is_denied(app, client):
    identity, _ = await prepared(app, client, ready=False)
    reader = await client.post(
        BASE + f"/report-runs/{identity}/gstr1-review",
        headers=headers(registrations=GSTR1_GST),
        json={"state": "REVIEWED", "reference": "Reader proof", "evidence_hash": "a" * 64},
    )
    assert reader.status_code == 403
    other_user = await client.get(
        BASE + f"/report-runs/{identity}/gstr1-records",
        headers=headers(registrations=GSTR1_GST, user=uuid.uuid4()),
    )
    assert other_user.status_code == 403
    denied_field = await client.get(
        BASE + f"/report-runs/{identity}/gstr1-records?q=INV",
        headers=headers(
            registrations=GSTR1_GST,
            policies=[
                {
                    "access": "read",
                    "effect": "deny",
                    "resource": "gst_outward_record",
                    "field": "taxable",
                }
            ],
        ),
    )
    assert denied_field.status_code == 403
    auth = headers(registrations=GSTR1_GST, permissions=PERMISSIONS | {"accounting.finance.manage"})
    result = await client.post(
        BASE + f"/report-runs/{identity}/gstr1-review",
        headers=auth,
        json={"state": "REVIEWED", "reference": "Missing proof", "evidence_hash": "a" * 64},
    )
    assert result.status_code == 409
    other = await client.get(
        BASE + "/report-definitions/GSTR1",
        headers=headers(registrations=(GSTR1_GST[0] | {"country_code": "US"},)),
    )
    assert other.status_code == 403


async def test_comparison_cannot_read_another_users_preparation(app, client):
    identity, prepared_job = await prepared(app, client)
    response = await client.post(
        BASE + "/report-runs",
        headers=headers(registrations=GSTR1_GST, user=uuid.uuid4()),
        json={
            "code": "GSTR1",
            "generation_id": prepared_job["generation_id"],
            "parameters": {
                "registration_id": REGISTRATION,
                "period": "2026-10",
                "comparison_job_id": identity,
            },
        },
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("obsolete", [False, True])
async def test_native_cut_resolves_amendment_history_and_detects_obsolete_baselines(
    app, client, obsolete
):
    original = document(return_date="2026-08-01", document_date="2026-08-01")
    previous = amendment(original, "1100", "198", return_date="2026-09-01")
    revised = amendment(original if obsolete else previous, "1200", "216")
    _, result = await prepared(
        app, client, outward=[*coverage([revised], sequence=1), original, previous]
    )
    if obsolete:
        assert "AMENDMENT_BASELINE_STALE" in {
            row["code"] for row in result["result"]["evidence"]["gstr1"]["issues"]
        }
    else:
        assert result["result"]["evidence"]["gstr1"]["bridge"]["3.1a"]["taxable"] == "100.00"


async def test_old_calculation_snapshot_is_readable_but_cannot_receive_new_review(
    app, client, monkeypatch
):
    monkeypatch.setattr("reports.domain.gstr1.CALCULATION_VERSION", 1)
    identity, _ = await prepared(app, client)
    visible = await client.get(
        BASE + f"/report-runs/{identity}", headers=headers(registrations=GSTR1_GST)
    )
    assert visible.status_code == 200
    result = await client.post(
        BASE + f"/report-runs/{identity}/gstr1-review",
        headers=headers(
            registrations=GSTR1_GST, permissions=PERMISSIONS | {"accounting.finance.manage"}
        ),
        json={"state": "REVIEWED", "reference": "Actual review proof", "evidence_hash": "a" * 64},
    )
    assert result.status_code == 409, result.text
