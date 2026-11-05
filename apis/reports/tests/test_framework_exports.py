import csv
import hashlib
import io
import uuid
import zipfile

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from sqlalchemy import select
from test_framework_execution import accepted, proof

from reports.models.export_artifacts import ReportExportArtifact
from reports.models.framework import ReportJob
from reports.queries.results import batches
from reports.tasks import export_artifacts as artifacts
from reports.tasks.framework_worker import process


async def authority(job):
    return proof(job)


@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "HTML", "PDF"])
async def test_outstanding_exports_identify_positive_debts_and_credits(
    app, client, tmp_path, format_name
):
    from test_native_ledger import prepared

    identities, _facts, _ids = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    path = f"/v2/companies/{COMPANY}/report-runs"
    created = await client.post(
        path,
        headers=headers(),
        json={
            "code": "OUTSTANDING_BILLS",
            "generation_id": str(identities[2]),
            "parameters": {"date_to": "2026-04-30"},
        },
    )
    assert created.status_code == 202, created.text
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created.json()["id"]),
        authority,
    )
    run = path + "/" + created.json()["id"]
    exported, target = await new_export(client, run, format_name)
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(exported["id"]),
        authority,
    )
    grant = await client.get(target + "/download-token", headers=headers())
    assert grant.status_code == 200, grant.text
    output = await client.get(
        target + "/download", headers=headers(), params={"token": grant.json()["token"]}
    )
    assert output.status_code == 200, output.text
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
        assert {(row["Direction"], row["Role"], row["Report Amount"]) for row in rows} == {
            ("DEBT", "CUSTOMER", "150.0000"),
            ("CREDIT", "CUSTOMER", "70.0000"),
        }
    else:
        if format_name == "XLSX":
            with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
                text = archive.read("xl/worksheets/sheet1.xml").decode()
        elif format_name == "PDF":
            from pypdf import PdfReader

            text = "".join(
                page.extract_text() for page in PdfReader(io.BytesIO(output.content)).pages
            )
        else:
            text = output.text
        for label in ("Direction", "Role", "DEBT", "CREDIT", "CUSTOMER"):
            assert label in text


async def test_export_source_label_uses_frozen_run_manifest(app, client, prefix, tmp_path):
    from sqlalchemy import update

    from reports.models.core import ReportGeneration

    run = await complete_run(app, client, prefix, tmp_path)
    frozen = (await client.get(run, headers=headers())).json()
    sequence = frozen["result"]["owner_manifest"]["sequence"]
    # Represent independent evolution of generation metadata; frozen run provenance wins.
    async with app.state.engine.begin() as connection:
        await connection.execute(
            update(ReportGeneration.__table__)
            .where(
                ReportGeneration.tenant_id == TENANT,
                ReportGeneration.company_id == COMPANY,
                ReportGeneration.id == uuid.UUID(frozen["generation_id"]),
            )
            .values(manifest=frozen["result"]["owner_manifest"] | {"sequence": sequence + 100})
        )
    created, target = await new_export(client, run, "HTML")
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    grant = (await client.get(target + "/download-token", headers=headers())).json()
    output = await client.get(
        target + "/download", headers=headers(), params={"token": grant["token"]}
    )
    assert f"Accounting sequence {sequence};" in output.text


async def complete_run(app, client, prefix, tmp_path):
    path, created = await accepted(app, client, prefix)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    return path + "/" + created["id"]


async def new_export(client, run, format_name="CSV"):
    key = headers()
    response = await client.post(run + "/exports", headers=key, json={"format": format_name})
    assert response.status_code == 202, response.text
    replay = await client.post(run + "/exports", headers=key, json={"format": format_name})
    assert replay.json()["id"] == response.json()["id"]
    return response.json(), f"/v2/companies/{COMPANY}/report-exports/{response.json()['id']}"


async def test_export_worker_publishes_owned_file_and_database_evidence(
    app, client, prefix, tmp_path
):
    from reports.tasks import framework_jobs as jobs
    from reports.tasks.export_worker import process as export

    run = await complete_run(app, client, prefix, tmp_path)
    created, target = await new_export(client, run)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            job = await jobs.claim(db, COMPANY, uuid.UUID(created["id"]))
        await export(app.state.session_factory, app.state.settings, job, authority)
    assert (await client.get(target, headers=headers())).json()["status"] == "COMPLETE"


@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "HTML", "PDF"])
async def test_export_is_independent_retained_exact_and_downloads_require_current_authority(
    app,
    client,
    prefix,
    tmp_path,
    format_name,
):
    run = await complete_run(app, client, prefix, tmp_path)
    created, target = await new_export(client, run, format_name)
    assert (await client.get(target + "/download-token", headers=headers())).status_code == 409
    identity = uuid.UUID(created["id"])
    for _ in range(2):
        await process(
            app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
        )
    result = await client.get(target, headers=headers())
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    evidence = result.json()["result"]
    assert "storage_key" not in str(evidence)
    assert result.json()["parent_id"] == run.rsplit("/", 1)[1]
    grant = await client.get(target + "/download-token", headers=headers())
    assert grant.status_code == 200, grant.text
    params = {"token": grant.json()["token"]}
    output = await client.get(target + "/download", headers=headers(), params=params)
    assert output.status_code == 200, output.text
    assert hashlib.sha256(output.content).hexdigest() == evidence["content_hash"]
    assert len(output.content) == evidence["byte_count"]
    if format_name == "CSV":
        rows = list(csv.reader(io.StringIO(output.content.decode("utf-8-sig"))))
        assert len(rows) - 1 == evidence["row_count"]
    elif format_name == "XLSX":
        with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
            assert archive.testzip() is None
            assert b"SOURCE_COUNT" in archive.read("xl/worksheets/sheet1.xml")
    elif format_name == "HTML":
        assert b"SOURCE_COUNT" in output.content and b"data-value=" in output.content
    else:
        from pypdf import PdfReader

        pdf = PdfReader(io.BytesIO(output.content))
        assert "SOURCE_COUNT" in "".join(page.extract_text() for page in pdf.pages)
    app.state.settings.exports_enabled = False
    assert (
        await client.get(target + "/download", headers=headers(), params=params)
    ).content == output.content
    for denied in (
        headers(user=uuid.uuid4()),
        headers(permissions=PERMISSIONS - {"report.export"}),
        headers(permissions=PERMISSIONS - {"ledger.read"}),
    ):
        assert (
            await client.get(target + "/download", headers=denied, params=params)
        ).status_code == 403
    other = uuid.uuid4()
    assert (
        await client.get(
            target.replace(str(COMPANY), str(other)) + "/download",
            headers=headers(company=other),
            params=params,
        )
    ).status_code == 403
    assert (await client.get(target + "/download", params=params)).status_code == 401
    assert (
        await client.get(target + "/download", headers=headers(), params={"token": "bad"})
    ).status_code == 422
    assert (await client.post(target + "/cancel", headers=headers())).status_code == 409
    assert (await client.get(run, headers=headers())).json()["status"] == "COMPLETE"
    assert list((tmp_path / "private" / "temporary").iterdir()) == []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            artifact = await db.scalar(select(ReportExportArtifact))
            assert artifact.state == "PUBLISHED" and artifact.row_count == evidence["row_count"]
            artifact.content_hash = "b" * 64
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
            await db.rollback()
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(ReportExportArtifact)) is None


async def test_revocation_cancel_and_oversized_exports_never_publish_partial_files(
    app,
    client,
    prefix,
    tmp_path,
):
    run = await complete_run(app, client, prefix, tmp_path)
    created, target = await new_export(client, run)
    await client.post(target + "/cancel", headers=headers())
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    assert (await client.get(target, headers=headers())).json()["status"] == "CANCELLED"
    app.state.settings.export_max_rows = 1
    oversized = await client.post(run + "/exports", headers=headers(), json={"format": "CSV"})
    assert oversized.status_code == 409
    app.state.settings.export_max_rows = 1000000
    created, target = await new_export(client, run)
    calls = 0

    async def revoked(job):
        nonlocal calls
        calls += 1
        return proof(job, allowed=calls < 2)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        revoked,
    )
    result = (await client.get(target, headers=headers())).json()
    assert result["status"] == "BLOCKED" and result["failure_code"] == "AUTHORITY_REVOKED"
    assert list((tmp_path / "private" / "objects").iterdir()) == []
    assert list((tmp_path / "private" / "temporary").iterdir()) == []
    assert (await client.get(run, headers=headers())).json()["status"] == "COMPLETE"


async def test_export_reader_reuses_retained_native_runtime_and_matches_api(app, client, tmp_path):
    from test_native_ledger import prepared

    identities, facts, ids = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    path = f"/v2/companies/{COMPANY}/report-runs"
    result = await client.post(
        path,
        headers=headers(),
        json={
            "code": "ACCOUNT_LEDGER",
            "generation_id": str(identities[2]),
            "parameters": {
                "date_from": "2026-04-01",
                "date_to": "2027-04-30",
                "comparative_from": "2026-04-01",
                "comparative_to": "2026-04-30",
            },
        },
    )
    assert result.status_code == 202, result.text
    identity = uuid.UUID(result.json()["id"])
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    run = path + "/" + str(identity)
    expected = (await client.get(run + "/rows", headers=headers(), params={"limit": 200})).json()[
        "items"
    ]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.get(ReportJob, identity)
            streamed = [row async for values in batches(db, job) for row in values]
    assert streamed == [row["data"] for row in expected]
    created, target = await new_export(client, run)
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    assert (await client.get(target, headers=headers())).json()["result"]["row_count"] == len(
        expected
    )


async def test_storage_failure_retries_with_a_new_key_and_cleanup_retains_completed_bytes(
    app,
    client,
    prefix,
    tmp_path,
    monkeypatch,
):
    from billing_platform.db.types import utcnow

    from reports.storage.filesystem import LocalArtifactStore
    from reports.tasks.artifact_cleanup import cleanup

    run = await complete_run(app, client, prefix, tmp_path)
    created, target = await new_export(client, run)
    identity = uuid.UUID(created["id"])
    original = LocalArtifactStore.publish
    attempts = 0

    def unavailable_once(self, *args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("test volume unavailable")
        return original(self, *args)

    monkeypatch.setattr(LocalArtifactStore, "publish", unavailable_once)
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    assert (await client.get(target, headers=headers())).json()["status"] == "QUEUED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            job = await db.get(ReportJob, identity)
            job.available_at = utcnow()
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    result = (await client.get(target, headers=headers())).json()
    assert result["status"] == "COMPLETE" and result["attempt"] == 2
    await cleanup(app.state.session_factory, app.state.settings, TENANT, COMPANY)
    assert len(list((tmp_path / "private" / "objects").iterdir())) == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            records = list(
                await db.scalars(
                    select(ReportExportArtifact).order_by(ReportExportArtifact.attempt)
                )
            )
            assert [row.state for row in records] == ["STAGING", "PUBLISHED"]
            assert len({row.storage_key for row in records}) == 2
            assert all(row.temporary_cleaned_at is not None for row in records)


async def test_cleanup_and_artifact_publication_fence_expired_attempts(
    app, client, prefix, tmp_path
):
    import datetime as dt

    from billing_platform.db.types import utcnow

    from reports.storage.filesystem import StoredObject
    from reports.tasks import framework_jobs as jobs
    from reports.tasks.artifact_cleanup import cleanup

    run = await complete_run(app, client, prefix, tmp_path)
    created, _ = await new_export(client, run)
    identity = uuid.UUID(created["id"])
    storage = artifacts.store(app.state.settings)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            job = await jobs.claim(db, COMPANY, identity)
            artifact = await artifacts.begin(
                db, job, artifacts.definition("CSV", app.state.settings)
            )
        output = storage.begin(artifact.storage_key)
        output.write_bytes(b"partial")
        async with app.state.session_factory() as db, db.begin():
            live = await db.get(ReportJob, identity)
            live.lease_until = utcnow() - dt.timedelta(seconds=1)
        report = await cleanup(app.state.session_factory, app.state.settings, TENANT, COMPANY)
        assert report["removed_temporary_folders"] == 0 and output.exists()
        async with app.state.session_factory() as db, db.begin():
            replacement = await jobs.claim(db, COMPANY, identity)
            assert replacement.attempt == 2
        async with app.state.session_factory() as db, db.begin():
            with pytest.raises(ConflictError):
                await artifacts.publish(
                    db, job, artifact.id, StoredObject(artifact.storage_key, 7, "a" * 64), 1
                )
            await db.rollback()
        report = await cleanup(app.state.session_factory, app.state.settings, TENANT, COMPANY)
        assert report["removed_temporary_folders"] == 1 and not output.exists()


async def test_staging_artifact_cannot_start_with_cleanup_evidence(
    app, client, prefix, tmp_path, monkeypatch
):
    from billing_platform.db.types import utcnow

    from reports.tasks import framework_jobs as jobs

    run = await complete_run(app, client, prefix, tmp_path)
    created, _ = await new_export(client, run)
    original = artifacts.ReportExportArtifact

    def prematurely_cleaned(**values):
        return original(**values, temporary_cleaned_at=utcnow())

    monkeypatch.setattr(artifacts, "ReportExportArtifact", prematurely_cleaned)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            job = await jobs.claim(db, COMPANY, uuid.UUID(created["id"]))
            with pytest.raises(ConflictError, match="staging"):
                await artifacts.begin(db, job, artifacts.definition("CSV", app.state.settings))
            await db.rollback()
