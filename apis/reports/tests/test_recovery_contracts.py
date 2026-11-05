"""Recovery must retain the last good generation and never publish partial outputs."""

import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT, headers
from fixtures import dataset, manifest
from pydantic import SecretStr
from reporting_contract.contract import FactPage
from reporting_contract.transport import Owner
from sqlalchemy import func, select, update
from test_foundation import generation, load

from reports.models import core as m
from reports.tasks import ingest, runs, worker
from reports.tasks.common import get


def owner():
    return Owner(
        origin="http://127.0.0.1",
        key_id="reports.recovery.test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )


async def test_owner_outage_and_invalid_run_preserve_good_outputs(app, client, prefix):
    first = await generation(client, prefix)
    await load(app, first["id"])
    pending = await generation(client, prefix)
    body = {
        "generation_id": first["id"],
        "code": "ACCOUNT_LEDGER",
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
    }
    good = await client.post(prefix + "/report-runs", headers=headers(), json=body)
    bad = await client.post(
        prefix + "/report-runs", headers=headers(), json=body | {"account_id": str(uuid.uuid4())}
    )
    assert good.status_code == bad.status_code == 202
    good_id, bad_id = good.json()["id"], bad.json()["id"]
    assert (
        await client.get(prefix + f"/report-runs/{good_id}/rows", headers=headers())
    ).status_code == 409

    def offline(request):
        raise httpx.ConnectError("owner unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as transport:
        await worker.poll(app.state.session_factory, transport, owner())
        await worker.poll(app.state.session_factory, transport, owner())
    good_result = await client.get(prefix + f"/report-runs/{good_id}", headers=headers())
    bad_result = await client.get(prefix + f"/report-runs/{bad_id}", headers=headers())
    assert good_result.json()["status"] == "COMPLETE"
    assert bad_result.json()["status"] == "BLOCKED"
    assert bad_result.json()["failure_code"] == "REPORT_VERIFICATION_FAILED"
    assert bad_result.json()["download_token"] is None
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            active = await db.scalar(select(m.ReportActivation))
            assert str(active.generation_id) == first["id"]
            queued = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(pending["id"]))
            assert queued.status == "PENDING" and queued.applied_sequence == 0
            assert (
                await db.scalar(
                    select(func.count(m.ReportRow.id)).where(
                        m.ReportRow.run_id == uuid.UUID(bad_id)
                    )
                )
                == 0
            )
            assert await db.scalar(select(func.count(m.ReportArtifact.id))) == 1
            await runs.complete(db, await get(db, COMPANY, m.ReportRun, uuid.UUID(good_id)))
            with pytest.raises(ConflictError, match="cannot be processed"):
                await runs.complete(db, await get(db, COMPANY, m.ReportRun, uuid.UUID(bad_id)))


async def test_page_scope_boundaries_and_replay_are_validated_before_checkpoint(
    app, client, prefix
):
    record = await generation(client, prefix)
    items = dataset()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(record["id"]))
            proof = manifest(items, identity=row.snapshot_id)
            with pytest.raises(ConflictError, match="scope"):
                await ingest.bundle(db, row, proof.model_copy(update={"company_id": uuid.uuid4()}))
            with pytest.raises(ConflictError, match="snapshot identity"):
                await ingest.bundle(db, row, proof.model_copy(update={"id": uuid.uuid4()}))
            with pytest.raises(ConflictError, match="sequence"):
                await ingest.bundle(db, row, manifest(items, sequence=2, kind="CHANGE"))
            bundle = await ingest.bundle(db, row, proof)
            with pytest.raises(ConflictError, match="identity changed"):
                await ingest.bundle(db, row, proof.model_copy(update={"sequence": 2}))
            invalid_pages = [
                (FactPage(manifest_id=uuid.uuid4(), items=items), 0),
                (FactPage(manifest_id=proof.id, items=items[:2]), 0),
                (FactPage(manifest_id=proof.id, items=items[:2], next_after=4), 0),
                (FactPage(manifest_id=proof.id, items=items[:2], next_after=4), 2),
                (FactPage(manifest_id=proof.id, items=[], next_after=2), 2),
            ]
            for page, after in invalid_pages:
                with pytest.raises(ConflictError):
                    await ingest.stage(db, bundle, page, after)
                assert bundle.last_ordinal == 0 and row.applied_sequence == 0
            first = FactPage(manifest_id=proof.id, items=items[:2], next_after=2)
            await ingest.stage(db, bundle, first, 0)
            await db.flush()
            with pytest.raises(ConflictError, match="duplicate source page changed"):
                await ingest.stage(
                    db, bundle, first.model_copy(update={"items": list(reversed(items[:2]))}), 0
                )
            assert bundle.last_ordinal == 2 and row.applied_sequence == 0
            with pytest.raises(ConflictError, match="committed barrier"):
                await ingest.activate(db, row)


async def test_frozen_output_survives_old_source_schema_but_new_render_fails_closed(
    app, client, prefix
):
    record = await generation(client, prefix)
    await load(app, record["id"])
    body = {"generation_id": record["id"]}
    made = await client.post(prefix + "/report-runs", headers=headers(), json=body)
    identity = uuid.UUID(made.json()["id"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await runs.complete(db, await get(db, COMPANY, m.ReportRun, identity))
            gen = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(record["id"]))
            old = gen.manifest | {"schema_hash": "0" * 64}
    # Seed an older deployment's persisted manifest in this disposable test database only.
    async with app.state.engine.begin() as connection:
        await connection.execute(
            update(m.ReportGeneration.__table__)
            .where(
                m.ReportGeneration.id == uuid.UUID(record["id"]),
                m.ReportGeneration.tenant_id == TENANT,
                m.ReportGeneration.company_id == COMPANY,
            )
            .values(manifest=old)
        )
    frozen = await client.get(prefix + f"/report-runs/{identity}", headers=headers())
    assert frozen.status_code == 200 and frozen.json()["status"] == "COMPLETE"
    downloaded = await client.get(
        prefix + f"/report-runs/{identity}/download",
        params={"token": frozen.json()["download_token"]},
        headers=headers(),
    )
    assert downloaded.status_code == 200 and "GL_CONTROL" in downloaded.text
    again = await client.post(prefix + "/report-runs", headers=headers(), json=body)
    async with httpx.AsyncClient() as transport:
        await worker.poll(app.state.session_factory, transport, owner())
    rejected = await client.get(prefix + "/report-runs/" + again.json()["id"], headers=headers())
    assert rejected.json()["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "extra",
    [
        {"comparative_from": "2026-04-01"},
        {"comparative_from": "2026-04-03", "comparative_to": "2026-04-01"},
        {"basis": "TRANSACTION"},
        {"code": "TRIAL_BALANCE", "account_id": str(uuid.uuid4())},
        {"code": "BANK_RECONCILIATION"},
        {
            "code": "BANK_RECONCILIATION",
            "account_id": str(uuid.uuid4()),
            "statement_balance": "NaN",
        },
    ],
)
async def test_incomplete_or_partial_report_queries_fail_before_creation(client, prefix, extra):
    response = await client.post(
        prefix + "/report-runs",
        headers=headers(),
        json={
            "generation_id": str(uuid.uuid4()),
            "code": "ACCOUNT_LEDGER",
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            **extra,
        },
    )
    assert response.status_code == 422


async def test_http_bounds_throttling_and_dependency_probe(client, app, prefix):
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    probe = await client.get("/health/ready")
    # SQLite fixtures have no Alembic table; native fixtures have the current migration head.
    assert probe.status_code in {200, 503}
    assert probe.headers["cache-control"] == "no-store"
    too_large = await client.post(prefix + "/report-generations", content=b" " * 262145)
    assert too_large.status_code == 413 and "payload_too_large" in too_large.text
    assert (await client.get(prefix + "/not-a-route")).status_code == 404
    from conftest import USER

    for _ in range(240):
        app.state.write_limiter.allow(f"{TENANT}:{COMPANY}:{USER}", limit=240)
    throttled = await client.post(prefix + "/report-generations", headers=headers(), json={})
    assert throttled.status_code == 429
