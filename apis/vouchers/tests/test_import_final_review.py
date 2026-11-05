"""Final review regressions: private templates, report locations and native races."""

import asyncio
import base64
import csv
import datetime as dt
import io
import uuid

import pytest
import test_imports_api as import_fixtures
from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_imports_api import auth, bill, purchase_type, upload, validated, voucher_count

from vouchers.models import imports as models
from vouchers.tasks import imports as run
from vouchers.tasks.import_extensions import render_data

masters = import_fixtures.masters


async def test_retained_revision_and_attempt_capacity_is_bounded(
    client, prefix, monkeypatch, masters
):
    from vouchers.tasks import import_history as journal

    kind = await purchase_type(client, prefix)
    job = (await upload(client, prefix, kind["id"], [bill("CAP")])).json()
    path = prefix + f"/voucher-imports/{job['id']}"
    monkeypatch.setattr(journal, "MAX_REVISIONS", 1)
    refused = await client.post(
        path + "/revisions",
        headers=auth(),
        json={
            "expected_version": job["row_version"],
            "voucher_type_id": kind["id"],
            "format": "JSON",
            "document": {"schema_version": 1, "vouchers": [bill("CAP")]},
        },
    )
    assert refused.status_code == 409 and "revision limit" in refused.text
    monkeypatch.setattr(journal, "MAX_ATTEMPTS", 0)
    refused = await client.post(
        path + "/validate", headers=auth(), json={"expected_version": job["row_version"]}
    )
    assert refused.status_code == 409 and "attempt limit" in refused.text
    assert (await client.get(path, headers=auth())).json()["state"] == "STAGED"


async def test_attempt_cannot_reference_another_jobs_revision(client, prefix, app):
    kind = await purchase_type(client, prefix)
    first = (await upload(client, prefix, kind["id"], [bill("ONE")])).json()
    second = (await upload(client, prefix, kind["id"], [bill("TWO")])).json()
    with tenant_scope(TENANT), pytest.raises(IntegrityError):
        async with app.state.session_factory() as db, db.begin():
            revision = await db.scalar(
                select(models.VoucherImportRevision).where(
                    models.VoucherImportRevision.job_id == uuid.UUID(first["id"])
                )
            )
            db.add(
                models.VoucherImportAttempt(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    job_id=uuid.UUID(second["id"]),
                    revision_id=revision.id,
                    phase="VALIDATE",
                    outcome="RUNNING",
                )
            )
            await db.flush()


@pytest.mark.parametrize(
    "positions", [[("CSV", 3), ("CSV", 4)], [("vouchers", 3), ("lines", 8), ("lines", 9)]]
)
def test_result_download_keeps_each_line_location_and_empty_vouchers(positions):
    data = render_data(
        [
            {
                "key": "A",
                "source": {"header": {}, "lines": [{"amount": "1"}, {"amount": "2"}]},
                "positions": positions,
            },
            {
                "key": "B",
                "source": {"header": {"narration": "missing lines"}, "lines": []},
                "positions": [("vouchers", 5)],
            },
        ],
        "CSV",
        {"A": {"state": "VALID"}, "B": {"state": "INVALID"}},
    )
    # Template marker precedes the actual header.
    rows = list(csv.DictReader(io.StringIO(data.decode().split("\n", 1)[1])))
    assert [row["import_key"] for row in rows] == ["A", "A", "B"]
    expected = positions[-2:]
    assert [(row["_source_sheet"], int(row["_source_row"])) for row in rows[:2]] == expected
    assert rows[2]["_status"] == "INVALID" and rows[2]["_source_row"] == "5"


async def test_snapshot_hides_optional_denied_defaults_and_stage_uses_dates(
    client, prefix, monkeypatch
):
    kind = await purchase_type(client, prefix)
    day = dt.date.today() - dt.timedelta(days=1)
    body = {
        "voucher_type_id": kind["id"],
        "document_date": day.isoformat(),
        "posting_date": day.isoformat(),
    }
    denied = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "narration",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    response = await client.post(
        prefix + "/voucher-import-template-snapshots", headers=auth(policies=denied), json=body
    )
    assert response.status_code == 403, response.text
    snapshot = await client.post(
        prefix + "/voucher-import-template-snapshots", headers=auth(), json=body
    )
    assert snapshot.status_code == 201, snapshot.text
    template = await client.get(
        prefix + "/voucher-import-templates", headers=auth(), params=body | {"format": "TSV"}
    )
    assert template.status_code == 200, template.text
    calls = []
    original = run.shape_for

    async def shape(*args, **kwargs):
        calls.append(kwargs)
        return await original(*args, **kwargs)

    monkeypatch.setattr(run, "shape_for", shape)
    staged = await client.post(
        prefix + "/voucher-imports",
        headers=auth(),
        json={
            "voucher_type_id": kind["id"],
            "template_id": snapshot.json()["id"],
            "format": "TSV",
            "content_base64": base64.b64encode(template.content).decode(),
        },
    )
    assert staged.status_code == 202, staged.text
    assert len(calls) >= 2 and all(call["document_date"] == day for call in calls)


@pytest.mark.mysql
async def test_concurrent_commit_has_one_attempt_and_effect(client, prefix, app, masters):
    if app.state.engine.dialect.name == "sqlite":
        pytest.skip("requires native row locks")
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("RACE")])).json()
    ready = await validated(client, prefix, job)
    path = prefix + f"/voucher-imports/{job['id']}"
    payload = {
        "expected_version": ready["row_version"],
        "selection_digest": ready["selection_digest"],
    }
    results = await asyncio.gather(
        *(client.post(path + "/commit", headers=auth(), json=payload) for _ in range(2))
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    assert await voucher_count(app) == 1
    attempts = (await client.get(path + "/history/attempts", headers=auth())).json()["items"]
    assert len([row for row in attempts if row["phase"] == "COMMIT"]) == 1
