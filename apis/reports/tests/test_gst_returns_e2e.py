"""Both returns share a verified native cut; approval and filing remain independent."""

import io
import json
import os
import uuid
from pathlib import Path

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from financial_fixture import financial_dataset, financial_manifest
from fixtures import source
from reporting_contract.gst import COVERAGE_AREAS, GstReturnRecord
from sqlalchemy import select
from test_framework_execution import proof
from test_gstr1_api import GSTR1_GST, REGISTRATION
from test_gstr1_calculation import coverage, document
from test_source_versions import staged

from reports.models.source_versions import ReportSourceCut
from reports.tasks.framework_worker import process
from reports.tasks.source_publication import publish

BASE = f"/v2/companies/{COMPANY}"


def auth(**extra):
    return headers(
        registrations=GSTR1_GST,
        permissions=PERMISSIONS | {"accounting.finance.manage"},
        **extra,
    )


async def cut(app, *, paid=True, outward_igst="180"):
    facts, _ = financial_dataset()
    for row in coverage([document(igst=outward_igst)], sequence=1):
        facts.append(
            source(
                "gst_outward_record",
                uuid.UUID(row["id"]),
                {key: value for key, value in row.items() if key != "id"},
            )
        )
    allocations = [
        ("3.1a", {"taxable": "1000", "igst": "180"}),
        ("GSTR1", {"taxable": "1000", "igst": "180"}),
        ("GSTR2B", {}),
        ("IMS", {}),
    ]
    if paid:
        allocations += [("CASH_DEPOSIT", {"igst": "180"}), ("OFFSET_NORMAL_CASH", {"igst": "180"})]
    allocations += [
        ("COVERAGE", {"coverage_area": area, "coverage_status": "COMPLETE", "covered_sequence": 1})
        for area in COVERAGE_AREAS
    ]
    for category, values in allocations:
        record = GstReturnRecord(
            registration_id=REGISTRATION,
            return_date="2026-10-01",
            event_date="2026-10-01",
            category=category,
            source_entity="EXTERNAL",
            reference="Reviewed source " + category,
            evidence_hash="a" * 64,
            explanation="Explicit reviewed statutory test evidence",
            **values,
        ).model_dump(mode="json")
        facts.append(source("gst_return_record", uuid.uuid4(), record))
    facts.sort(key=lambda row: (row.entity, str(row.source_id)))
    identities, _ = await staged(app, source=facts, control=financial_manifest(facts).control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            retained = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, retained.id)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    return str(identities[2])


async def prepare(app, client, generation, code, comparison=None):
    result = await client.post(
        BASE + "/report-runs",
        headers=auth(),
        json={
            "code": code,
            "generation_id": generation,
            "parameters": {
                "registration_id": REGISTRATION,
                "period": "2026-10",
                **({"comparison_job_id": comparison} if comparison else {}),
            },
        },
    )
    assert result.status_code == 202, result.text

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(result.json()["id"]),
        authority,
    )
    frozen = await client.get(BASE + "/report-runs/" + result.json()["id"], headers=auth())
    assert frozen.json()["status"] == "COMPLETE", frozen.text
    return frozen.json()


async def review(client, job, code, state):
    path = "gstr1-review" if code == "GSTR1" else "gst-review"
    return await client.post(
        BASE + "/report-runs/" + job["id"] + "/" + path,
        headers=auth(),
        json={
            "state": state,
            "reference": "Retained " + code + " proof",
            "evidence_hash": "b" * 64,
            **({"filed_date": "2026-11-01"} if state == "EXTERNALLY_FILED" else {}),
        },
    )


@pytest.mark.parametrize("paid", [False, True])
async def test_same_native_cut_reconciles_both_returns_and_keeps_filing_controls_separate(
    app, client, tmp_path, paid
):
    generation = await cut(app, paid=paid)
    three_b = await prepare(app, client, generation, "GSTR3B")
    one = await prepare(app, client, generation, "GSTR1", three_b["id"])
    for job, key in ((three_b, "gstr3b"), (one, "gstr1")):
        evidence = job["result"]["evidence"][key]
        assert evidence["issues"] == [], evidence["issues"]
        assert evidence["reconciliation"]
        assert all(row["difference"] == "0.00" for row in evidence["reconciliation"])
    for job, code in ((one, "GSTR1"), (three_b, "GSTR3B")):
        approved = await review(client, job, code, "REVIEWED")
        assert approved.status_code == 201, approved.text
        replay = await review(client, job, code, "REVIEWED")
        assert replay.json()["id"] == approved.json()["id"]
        filed = await review(client, job, code, "EXTERNALLY_FILED")
        assert filed.status_code == (409 if code == "GSTR3B" and not paid else 201), filed.text
    if paid:
        app.state.settings.exports_enabled = True
        app.state.settings.artifact_root = tmp_path / "private"
        for job in (one, three_b):
            for export_format in ("PDF", "XLSX", "CSV"):
                created = await client.post(
                    BASE + "/report-runs/" + job["id"] + "/exports",
                    headers=auth(),
                    json={"format": export_format},
                )
                assert created.status_code == 202, created.text

                async def authority(export_job):
                    return proof(export_job)

                await process(
                    app.state.session_factory,
                    app.state.settings,
                    TENANT,
                    COMPANY,
                    uuid.UUID(created.json()["id"]),
                    authority,
                )
                target = BASE + "/report-exports/" + created.json()["id"]
                status = await client.get(target, headers=auth())
                assert status.json()["status"] == "COMPLETE", status.text
                assert (
                    await client.get(target + "/download-token", headers=auth(user=uuid.uuid4()))
                ).status_code == 403
                token = await client.get(target + "/download-token", headers=auth())
                downloaded = await client.get(
                    target + "/download", headers=auth(), params={"token": token.json()["token"]}
                )
                assert downloaded.status_code == 200
                assert len(downloaded.content) > 100
                if os.environ.get("GST_E2E_EVIDENCE_DIR"):
                    destination = Path(os.environ["GST_E2E_EVIDENCE_DIR"]) / job["code"]
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / ("preparation." + export_format.lower())).write_bytes(
                        downloaded.content
                    )
                    (destination / "preparation.json").write_text(json.dumps(job), encoding="utf-8")
                    records_path = "gstr1-records" if job["code"] == "GSTR1" else "gst-records"
                    records = await client.get(
                        BASE + "/report-runs/" + job["id"] + "/" + records_path, headers=auth()
                    )
                    assert records.status_code == 200, records.text
                    (destination / "rows.json").write_text(
                        json.dumps(records.json()), encoding="utf-8"
                    )
                if export_format == "PDF":
                    assert downloaded.content.startswith(b"%PDF")
                    if job["code"] == "GSTR1":
                        from pypdf import PdfReader

                        last_page = (
                            PdfReader(io.BytesIO(downloaded.content)).pages[-1].extract_text()
                        )
                        assert "GSTR3B" in last_page and "Verification" in last_page
                elif export_format == "XLSX":
                    assert downloaded.content.startswith(b"PK")
                else:
                    assert "1000.00" in downloaded.text
        for code in ("GSTR1", "GSTR3B"):
            blocked = await client.post(
                BASE + "/report-runs",
                headers=auth(),
                json={
                    "code": code,
                    "generation_id": generation,
                    "parameters": {"registration_id": REGISTRATION, "period": "2026-10"},
                },
            )
            assert blocked.status_code == 409, blocked.text


async def test_joint_comparison_difference_blocks_gstr1_review(app, client):
    generation = await cut(app, outward_igst="181")
    three_b = await prepare(app, client, generation, "GSTR3B")
    one = await prepare(app, client, generation, "GSTR1", three_b["id"])
    evidence = one["result"]["evidence"]["gstr1"]
    assert any(
        row["source"] == "GSTR3B" and row["head"] == "IGST" and row["difference"] == "1.00"
        for row in evidence["reconciliation"]
    )
    assert (await review(client, one, "GSTR1", "REVIEWED")).status_code == 409


async def test_old_3b_calculations_cannot_be_used_for_a_new_gstr1_comparison(
    app, client, monkeypatch
):
    generation = await cut(app)
    with monkeypatch.context() as archived:
        archived.setattr("reports.domain.gstr3b.CALCULATION_VERSION", 0)
        three_b = await prepare(app, client, generation, "GSTR3B")
    result = await client.post(
        BASE + "/report-runs",
        headers=auth(),
        json={
            "code": "GSTR1",
            "generation_id": generation,
            "parameters": {
                "registration_id": REGISTRATION,
                "period": "2026-10",
                "comparison_job_id": three_b["id"],
            },
        },
    )
    assert result.status_code == 409, result.text


@pytest.mark.parametrize("code", ["GSTR1", "GSTR3B"])
async def test_joint_cut_keeps_actor_and_field_denies_on_retained_records(app, client, code):
    generation = await cut(app)
    job = await prepare(app, client, generation, code)
    path = "gstr1-records" if code == "GSTR1" else "gst-records"
    endpoint = BASE + "/report-runs/" + job["id"] + "/" + path
    assert (await client.get(endpoint, headers=auth(user=uuid.uuid4()))).status_code == 403
    denied = await client.get(
        endpoint,
        headers=auth(
            policies=[
                {
                    "access": "read",
                    "effect": "deny",
                    "resource": "gst_outward_record" if code == "GSTR1" else "gst_return_record",
                    "field": "taxable",
                }
            ]
        ),
    )
    assert denied.status_code == 403, denied.text
    app.state.settings.exports_enabled = True
    blocked = await client.post(
        BASE + "/report-runs/" + job["id"] + "/exports",
        headers=auth(
            policies=[
                {
                    "access": "read",
                    "effect": "deny",
                    "resource": "gst_outward_record" if code == "GSTR1" else "gst_return_record",
                    "field": "taxable",
                }
            ]
        ),
        json={"format": "CSV"},
    )
    assert blocked.status_code == 403, blocked.text
