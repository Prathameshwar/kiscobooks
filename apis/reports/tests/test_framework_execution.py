import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from reporting_contract.authority import ReportAuthority
from sqlalchemy import func, select, update
from test_foundation import generation, load

from reports.models.framework import ReportJob, ReportResultBatch
from reports.tasks.framework_worker import process


def proof(job, *, allowed=True):
    now = utcnow()
    return ReportAuthority(
        request_id=uuid.uuid4(),
        tenant_id=job.tenant_id,
        company_id=job.company_id,
        user_id=job.actor_id,
        source_version=1,
        generated_at=now,
        expires_at=now + dt.timedelta(seconds=30),
        permissions=PERMISSIONS,
        read_allowed=allowed,
    )


async def accepted(app, client, prefix):
    app.state.settings.framework_enabled = True
    source = await generation(client, prefix)
    await load(app, source["id"])
    path = f"/v2/companies/{COMPANY}/report-runs"
    key = headers()
    body = {"code": "SOURCE_RECONCILIATION", "generation_id": source["id"]}
    first = await client.post(path, headers=key, json=body)
    assert first.status_code == 202, first.text
    repeat = await client.post(path, headers=key, json=body)
    assert repeat.json()["id"] == first.json()["id"]
    return path, first.json()


@pytest.mark.parametrize("insufficient", [False, True])
async def test_invalid_frozen_filter_is_blocked_without_dependency_retry(
    app, client, prefix, monkeypatch, insufficient
):
    from billing_platform.errors import ValidationFailedError

    from reports.domain.reporting.history_coverage import InsufficientHistoryError
    from reports.tasks import framework_worker

    path, created = await accepted(app, client, prefix)

    async def invalid(*args):
        if insufficient:
            raise InsufficientHistoryError("requested history precedes retained owner coverage")
        raise ValidationFailedError("report filter is outside the frozen company source")

    async def authority(job):
        return proof(job)

    monkeypatch.setattr(framework_worker, "load", invalid)
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    result = (await client.get(path + "/" + created["id"], headers=headers())).json()
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == (
        "INSUFFICIENT_ACCOUNTING_HISTORY" if insufficient else "REPORT_VERIFICATION_FAILED"
    )
    assert result["attempt"] == 1


async def test_run_admission_worker_publication_pagination_and_current_permissions(
    app, client, prefix
):
    path, created = await accepted(app, client, prefix)
    identity = uuid.UUID(created["id"])
    target = path + "/" + str(identity)
    assert (await client.get(target + "/rows", headers=headers())).status_code == 409

    async def authority(job):
        return proof(job)

    for _ in range(2):
        await process(
            app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
        )
    result = await client.get(target, headers=headers())
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    assert result.json()["result"]["content_hash"]
    collected, cursor = [], None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = await client.get(target + "/rows", headers=headers(), params=params)
        assert page.status_code == 200, page.text
        collected.extend(page.json()["items"])
        cursor = page.json()["page"]["next_cursor"]
        if cursor is None:
            break
    assert len(collected) == result.json()["completed_rows"]
    assert [row["ordinal"] for row in collected] == list(range(1, len(collected) + 1))
    assert (await client.get(target, headers=headers(user=uuid.uuid4()))).status_code == 403
    revoked = headers(permissions=PERMISSIONS - {"ledger.read"})
    assert (await client.get(target + "/rows", headers=revoked)).status_code == 403
    assert (await client.post(target + "/cancel", headers=headers())).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportJob.id))) == 1


async def test_revoked_before_work_or_publication_never_exposes_partial_results(
    app, client, prefix
):
    path, created = await accepted(app, client, prefix)
    identity = uuid.UUID(created["id"])
    calls = 0

    async def authority(job):
        nonlocal calls
        calls += 1
        return proof(job, allowed=calls < 3)

    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    target = path + "/" + str(identity)
    response = (await client.get(target, headers=headers())).json()
    assert response["status"] == "BLOCKED" and response["result"] is None
    assert response["failure_code"] == "AUTHORITY_REVOKED"
    assert (await client.get(target + "/rows", headers=headers())).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportResultBatch.id))) == 1


async def test_cancelled_queued_job_and_invalid_parameters(app, client, prefix):
    path, created = await accepted(app, client, prefix)
    target = path + "/" + created["id"]
    token = headers()
    for _ in range(2):
        response = await client.post(target + "/cancel", headers=token)
        assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    assert (await client.post(target + "/retry", headers=headers())).status_code == 409
    assert (await client.get(target)).status_code == 401
    invalid = await client.post(
        path,
        headers=headers(),
        json={
            "code": "SOURCE_RECONCILIATION",
            "generation_id": created["generation_id"],
            "parameters": {"currency": "USD"},
        },
    )
    assert invalid.status_code == 422


async def test_framework_objects_reject_wrong_company_and_source_permissions(app, client, prefix):
    path, created = await accepted(app, client, prefix)
    other = uuid.uuid4()
    target = path.replace(str(COMPANY), str(other)) + "/" + created["id"]
    for suffix in ("", "/rows"):
        assert (
            await client.get(target + suffix, headers=headers(company=other))
        ).status_code == 403
    for action in ("cancel", "retry"):
        assert (
            await client.post(target + "/" + action, headers=headers(company=other))
        ).status_code == 403
    assert (
        await client.post(
            path,
            headers=headers(permissions=frozenset({"report.read"})),
            json={"code": "SOURCE_RECONCILIATION", "generation_id": created["generation_id"]},
        )
    ).status_code == 403


@pytest.mark.parametrize("failure,expected", [("view", 422), ("schema", 409)])
async def test_admission_rejects_unknown_views_and_unsupported_source_schemas(
    app, client, prefix, failure, expected
):
    from reports.models.core import ReportGeneration

    path, created = await accepted(app, client, prefix)
    body = {"code": "SOURCE_RECONCILIATION", "generation_id": created["generation_id"]}
    if failure == "view":
        body["view"] = "unregistered"
    else:
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                source = await db.get(ReportGeneration, uuid.UUID(created["generation_id"]))
                old = source.manifest | {"schema_hash": "0" * 64}
        # Represent an earlier deployment's retained schema in this disposable fixture only.
        async with app.state.engine.begin() as connection:
            await connection.execute(
                update(ReportGeneration.__table__)
                .where(
                    ReportGeneration.id == uuid.UUID(created["generation_id"]),
                    ReportGeneration.tenant_id == TENANT,
                    ReportGeneration.company_id == COMPANY,
                )
                .values(manifest=old)
            )
    response = await client.post(path, headers=headers(), json=body)
    assert response.status_code == expected, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportJob.id))) == 1


async def test_worker_version_mismatch_does_not_masquerade_as_bad_accounting_data(
    app, client, prefix, monkeypatch
):
    from dataclasses import replace
    from types import SimpleNamespace

    from reports.tasks import framework_worker

    path, created = await accepted(app, client, prefix)
    entry = framework_worker.catalog().resolve("SOURCE_RECONCILIATION")
    changed = replace(entry, definition=replace(entry.definition, implementation_hash="f" * 64))
    monkeypatch.setattr(
        framework_worker, "catalog", lambda: SimpleNamespace(resolve=lambda *args: changed)
    )

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    result = (await client.get(path + "/" + created["id"], headers=headers())).json()
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "REPORT_IMPLEMENTATION_UNAVAILABLE"
