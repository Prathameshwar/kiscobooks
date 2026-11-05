import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from fixtures import dataset, manifest, source
from reporting_contract.contract import FactPage
from sqlalchemy import func, select

from reports.models import core as m
from reports.tasks import ingest, runs
from reports.tasks.common import company_lock, get


async def generation(client, prefix):
    response = await client.post(prefix + "/report-generations", headers=headers(), json={})
    assert response.status_code == 202, response.text
    return response.json()


async def load(app, identity, items=None):
    items = items or dataset()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await company_lock(db, TENANT, COMPANY)
            row = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(identity), lock=True)
            evidence = manifest(items, identity=row.snapshot_id)
            bundle = await ingest.bundle(db, row, evidence)
            await ingest.stage(db, bundle, FactPage(manifest_id=evidence.id, items=items), 0)
            await db.flush()
            await ingest.apply(db, row, bundle)
            await db.flush()
            row.target_sequence = row.applied_sequence
            await ingest.activate(db, row)
    return items


async def test_full_api_run_pages_download_and_idempotency(client, prefix, app):
    key = headers()
    first = await client.post(prefix + "/report-generations", headers=key, json={})
    retry = await client.post(prefix + "/report-generations", headers=key, json={})
    assert first.status_code == 202, first.text
    assert first.json()["id"] == retry.json()["id"]
    identity = first.json()["id"]
    await load(app, identity)
    body = {"generation_id": identity}
    key = headers()
    created = await client.post(prefix + "/report-runs", headers=key, json=body)
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await runs.complete(db, await get(db, COMPANY, m.ReportRun, uuid.UUID(run_id)))
    replay = await client.post(prefix + "/report-runs", headers=key, json=body)
    assert replay.json()["id"] == run_id
    result = await client.get(prefix + "/report-runs/" + run_id, headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    assert result.json()["evidence"]["base_totals"]["INR"]["DEBIT"] == "100.0000"
    rows = await client.get(prefix + "/report-runs/" + run_id + "/rows?limit=2", headers=headers())
    assert rows.status_code == 200, rows.text
    cursor = rows.json()["page"]["next_cursor"]
    more = await client.get(
        prefix + "/report-runs/" + run_id + "/rows",
        params={"limit": 2, "cursor": cursor},
        headers=headers(),
    )
    assert more.json()["items"][0]["id"] != rows.json()["items"][0]["id"]
    downloaded = await client.get(
        prefix + "/report-runs/" + run_id + "/download",
        params={"token": result.json()["download_token"]},
        headers=headers(),
    )
    assert downloaded.status_code == 200 and "GL_CONTROL" in downloaded.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.ReportLine.id))) == 2
            assert await db.scalar(select(func.count(m.ReportAccountTotal.id))) == 2
            assert await db.scalar(select(func.count(m.ReportRun.id))) == 1
            from reports.models import BUSINESS_MODELS

            for model in BUSINESS_MODELS:
                assert await db.scalar(select(func.count(model.id))) > 0
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            for model in BUSINESS_MODELS:
                assert await db.scalar(select(func.count(model.id))) == 0


async def test_auth_scope_and_no_partial_totals(client, prefix, app):
    assert (await client.get(prefix + "/report-definitions")).status_code == 401
    assert (
        await client.get(
            prefix + "/report-definitions", headers=headers(permissions=frozenset({"report.read"}))
        )
    ).status_code == 403
    row = await generation(client, prefix)
    other = uuid.uuid4()
    assert (
        await client.get(
            prefix.replace(str(COMPANY), str(other)) + "/report-generations/" + row["id"],
            headers=headers(company=other),
        )
    ).status_code == 403
    assert (
        await client.get(
            prefix + "/report-generations/" + row["id"], headers=headers(tenant=uuid.uuid4())
        )
    ).status_code == 404
    deny = {
        "entity_type": "accounting.account",
        "field_key": "name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await client.get(prefix + "/report-definitions", headers=headers(policies=[deny]))
    ).status_code == 403
    assert (
        await client.post(
            prefix + "/report-runs", headers=headers(), json={"generation_id": row["id"]}
        )
    ).status_code == 409
    assert (
        await client.post(
            prefix + "/report-runs",
            headers=headers(),
            json={"generation_id": row["id"], "code": "BALANCE_SHEET"},
        )
    ).status_code == 422


async def test_bundle_pages_duplicate_conflict_and_atomic_checkpoint(app, client, prefix):
    record = await generation(client, prefix)
    items = dataset()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(record["id"]))
            evidence = manifest(items, identity=row.snapshot_id)
            bundle = await ingest.bundle(db, row, evidence)
            page = FactPage(manifest_id=evidence.id, items=items[:3], next_after=3)
            await ingest.stage(db, bundle, page, 0)
            await db.flush()
            await ingest.stage(db, bundle, page, 0)
            with pytest.raises(ConflictError):
                await ingest.apply(db, row, bundle)
            assert row.applied_sequence == 0
            await ingest.stage(db, bundle, FactPage(manifest_id=evidence.id, items=items[3:]), 3)
            await db.flush()
            await ingest.apply(db, row, bundle)
            await db.flush()
            await ingest.apply(db, row, bundle)
            assert row.applied_sequence == 1
            assert await db.scalar(select(func.count(m.ReportFact.id))) == len(items)


async def test_failed_reconciliation_keeps_prior_active_generation(app, client, prefix):
    first = await generation(client, prefix)
    items = await load(app, first["id"])
    second = await generation(client, prefix)
    broken = [row for row in items if row.entity != "account"]
    with pytest.raises(ConflictError):
        await load(app, second["id"], broken)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            active = await db.scalar(select(m.ReportActivation))
            assert str(active.generation_id) == first["id"]
            assert await db.scalar(select(func.count(m.ReportLine.id))) == 2


async def test_ready_generations_and_artifacts_cannot_be_changed(app, client, prefix):
    row = await generation(client, prefix)
    await load(app, row["id"])
    with tenant_scope(TENANT):
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                gen = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(row["id"]))
                gen.applied_sequence = 12
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                fact = await db.scalar(select(m.ReportFact))
                fact.data = {}


async def test_conflicting_posted_source_cannot_overwrite_during_catchup(app, client, prefix):
    record = await generation(client, prefix)
    items = dataset()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(record["id"]))
            evidence = manifest(items, identity=row.snapshot_id)
            bundle = await ingest.bundle(db, row, evidence)
            await ingest.stage(db, bundle, FactPage(manifest_id=evidence.id, items=items), 0)
            await db.flush()
            await ingest.apply(db, row, bundle)
            await db.flush()
            old = next(item for item in items if item.entity == "journal_line")
            changed = source(old.entity, old.source_id, old.data | {"base_amount": "200.0000"})
            proof = manifest([changed], sequence=2, kind="CHANGE", full=items)
            next_bundle = await ingest.bundle(db, row, proof)
            await ingest.stage(db, next_bundle, FactPage(manifest_id=proof.id, items=[changed]), 0)
            await db.flush()
            with pytest.raises(ConflictError, match="committed source content changed"):
                await ingest.apply(db, row, next_bundle)
            assert row.applied_sequence == 1


async def test_lean_lists_metadata_cursors_and_live_download_revocation(app, client, prefix):
    first = await generation(client, prefix)
    await generation(client, prefix)
    response = await client.get(prefix + "/report-generations?limit=1", headers=headers())
    assert response.status_code == 200, response.text
    assert "manifest" not in response.json()["items"][0]
    cursor = response.json()["page"]["next_cursor"]
    assert cursor
    following = await client.get(
        prefix + "/report-generations", params={"limit": 1, "cursor": cursor}, headers=headers()
    )
    assert following.json()["items"][0]["id"] != response.json()["items"][0]["id"]
    assert (
        await client.get(prefix + "/report-generations?arbitrary=true", headers=headers())
    ).status_code == 422
    assert (
        await client.get(
            prefix + "/report-generations",
            params={"limit": 1, "cursor": cursor + "x"},
            headers=headers(),
        )
    ).status_code == 422
    assert (
        await client.get(
            prefix + "/report-definitions/SOURCE_RECONCILIATION/field-set", headers=headers()
        )
    ).json()["complete_input_required"]
    assert (
        await client.get(
            prefix + "/report-definitions/UNSUPPORTED_REPORT/field-set", headers=headers()
        )
    ).status_code == 422
    await load(app, first["id"])
    created = await client.post(
        prefix + "/report-runs", json={"generation_id": first["id"]}, headers=headers()
    )
    run_id = created.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await runs.complete(db, await get(db, COMPANY, m.ReportRun, uuid.UUID(run_id)))
    result = await client.get(prefix + "/report-runs/" + run_id, headers=headers())
    token = result.json()["download_token"]
    from conftest import PERMISSIONS

    assert (
        await client.get(
            prefix + "/report-runs/" + run_id + "/download",
            params={"token": token},
            headers=headers(permissions=PERMISSIONS - {"report.export"}),
        )
    ).status_code == 403
    assert (
        await client.get(
            prefix + "/report-runs/" + run_id + "/download",
            params={"token": token},
            headers=headers(user=uuid.uuid4()),
        )
    ).status_code == 422
    assert (
        await client.get(prefix + "/report-runs/" + run_id, headers=headers(user=uuid.uuid4()))
    ).status_code == 403
    own = (await client.get(prefix + "/report-runs", headers=headers())).json()
    other = (await client.get(prefix + "/report-runs", headers=headers(user=uuid.uuid4()))).json()
    assert len(own["items"]) == 1 and other["items"] == []


async def test_native_fx_projection_keeps_zero_transaction_amount(app, client, prefix):
    record = await generation(client, prefix)
    items = dataset()
    party = uuid.uuid4()
    values = []
    for item in items:
        if item.entity == "journal_line":
            values.append(
                source(
                    item.entity,
                    item.source_id,
                    item.data
                    | {
                        "component": "FX",
                        "amount": "0.0000",
                        "party_id": str(party),
                        "role": "CUSTOMER",
                    },
                )
            )
        elif item.entity == "account":
            values.append(
                source(
                    item.entity,
                    item.source_id,
                    item.data | {"kind": "PARTY", "party_id": str(party), "party_role": "CUSTOMER"},
                )
            )
        else:
            values.append(item)
    values.append(
        source(
            "party",
            party,
            {"code": "FX", "name": "Party", "party_type": "ORGANISATION", "status": "ACTIVE"},
        )
    )
    await load(app, record["id"], values)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            lines = list(await db.scalars(select(m.ReportLine)))
            assert len(lines) == 2 and all(
                line.amount == 0 and line.base_amount == 100 and line.component == "FX"
                for line in lines
            )
