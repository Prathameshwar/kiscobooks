import asyncio
import datetime as dt
import hashlib
import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from reporting_contract.contract import FactPage, digest
from reporting_contract.snapshots import SnapshotStatus
from reporting_contract.transport import Owner, request
from sqlalchemy import func, select

from accounting.models.masters import Account
from accounting.models.reporting_snapshot import ReportSnapshotBatch, ReportSnapshotBuild
from accounting.tasks import reporting_feed as feed
from accounting.tasks.reporting_snapshot import build, get, read_view, store
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import fiscal_setup


async def admitted(app, client):
    await fiscal_setup(client)
    secret = SecretStr(secrets.token_hex(32))
    scopes = (CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),)
    app.state.settings.report_credentials["reports.test"] = SnapshotCredential(
        secret=secret, scopes=scopes
    )
    app.state.settings.report_snapshot_enabled = True
    owner = Owner(origin="http://127.0.0.1", key_id="reports.test", secret=secret, scopes=scopes)
    identity = uuid.uuid4()
    path = f"/internal/v2/reporting/{TENANT}/{COMPANY}/snapshots/{identity}"
    for _ in range(2):
        result = SnapshotStatus.model_validate(await request(client, owner, "POST", path))
        assert result.id == identity and result.status == "QUEUED" and result.manifest is None
    return owner, identity, path


async def test_catalog_outage_preserves_snapshot_integrity_attempts(app, client, monkeypatch):
    from accounting.tasks import stock_summary_source
    from accounting.tasks.reporting_snapshot import cycle_company

    _, identity, _ = await admitted(app, client)

    async def unavailable(*args):
        raise httpx.ConnectError("test dependency outage")

    monkeypatch.setattr(stock_summary_source, "prepare", unavailable)
    for _ in range(4):
        await cycle_company(
            app.state.engine, app.state.session_factory, app.state.settings, TENANT, COMPANY
        )
        with tenant_scope(TENANT):
            async with app.state.session_factory.begin() as db:
                row = await get(db, COMPANY, identity)
                assert row.status == "QUEUED"
                assert row.attempt == 0 and row.completed_facts == 0
                assert row.failure_code == "DEPENDENCY_UNAVAILABLE"
                row.lease_until = utcnow() - dt.timedelta(seconds=1)


async def test_snapshot_admission_authorization_capacity_and_partial_visibility(app, client):
    owner, identity, path = await admitted(app, client)
    assert (await client.post(path)).status_code == 401
    with pytest.raises(httpx.HTTPStatusError) as error:
        await request(client, owner, "GET", path.replace(str(COMPANY), str(uuid.uuid4())))
    assert error.value.response.status_code == 401
    with pytest.raises(httpx.HTTPStatusError) as error:
        await request(client, owner, "GET", path + "/facts")
    assert error.value.response.status_code == 409
    with pytest.raises(httpx.HTTPStatusError) as error:
        await request(client, owner, "GET", path + "/facts", {"limit": "201"})
    assert error.value.response.status_code == 422
    await request(client, owner, "POST", path.replace(str(identity), str(uuid.uuid4())))
    with pytest.raises(httpx.HTTPStatusError) as error:
        await request(client, owner, "POST", path.replace(str(identity), str(uuid.uuid4())))
    assert error.value.response.status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportSnapshotBuild.id))) == 2


async def test_snapshot_batch_scope_fencing_and_immutable_publication(app, client):
    _, identity, _ = await admitted(app, client)
    factory = app.state.session_factory
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            row = await get(db, COMPANY, identity)
            row.status, row.attempt = "RUNNING", 1
            row.lease_until = utcnow() + dt.timedelta(seconds=60)
            account = await db.scalar(select(Account).limit(1))
            wire = feed.fact(account, "account", account.id).model_dump(mode="json")
        await store(factory, COMPANY, identity, 1, 1, [wire])
        with pytest.raises(ConflictError):
            await store(factory, COMPANY, identity, 1, 3, [wire])
        async with factory() as db, db.begin():
            row = await get(db, COMPANY, identity)
            row.attempt = 2
        with pytest.raises(ConflictError):
            await store(factory, COMPANY, identity, 1, 2, [wire])
        async with factory() as db, db.begin():
            row = await get(db, COMPANY, identity)
            row.status, row.lease_until = "COMPLETE", None
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                row = await get(db, COMPANY, identity)
                row.status = "RUNNING"
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                row = await get(db, COMPANY, identity)
                db.expire(row, ["status"])
                row.status = "RUNNING"
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                row = await db.scalar(select(ReportSnapshotBatch))
                row.facts = []
    other = uuid.uuid4()
    with tenant_scope(other):
        async with factory() as db, db.begin():
            for model in (ReportSnapshotBuild, ReportSnapshotBatch):
                assert await db.scalar(select(func.count(model.id))) == 0
            foreign = ReportSnapshotBuild(
                tenant_id=other,
                company_id=COMPANY,
                status="RUNNING",
                attempt=1,
                lease_until=utcnow() + dt.timedelta(seconds=60),
            )
            db.add(foreign)
            await db.flush()
            db.add(
                ReportSnapshotBatch(
                    tenant_id=other,
                    company_id=COMPANY,
                    build_id=foreign.id,
                    attempt=1,
                    first_ordinal=1,
                    fact_count=1,
                    facts=[wire],
                    content_hash=digest([wire]),
                )
            )
    with tenant_scope(TENANT):
        async with factory() as db:
            assert await db.scalar(select(func.count(ReportSnapshotBuild.id))) == 1
            assert await db.scalar(select(func.count(ReportSnapshotBatch.id))) == 1


@pytest.mark.mysql
async def test_owner_read_view_releases_fence_while_preserving_cutoff(app, client, engine):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("native MVCC evidence")
    await fiscal_setup(client)
    factory = app.state.session_factory
    with tenant_scope(TENANT):
        async with read_view(engine, factory, COMPANY) as (reader, _setup, sequence, held):
            account = await reader.scalar(select(Account).limit(1))
            identity, original = account.id, account.name

            async def post():
                async with factory() as writer, writer.begin():
                    row = await writer.get(Account, identity)
                    row.name = "After the released snapshot fence"
                    row.row_version += 1

            await asyncio.wait_for(post(), 5)
            await reader.refresh(account)
            assert account.name == original
            assert (await reader.run_sync(lambda db: feed.head(db, COMPANY))).sequence == sequence
            assert held < 1
        async with factory() as db:
            assert (await db.get(Account, identity)).name == "After the released snapshot fence"
            assert (
                await db.run_sync(lambda sync: feed.head(sync, COMPANY))
            ).sequence == sequence + 1


@pytest.mark.mysql
async def test_native_snapshot_complete_pages_match_legacy_and_survive_reexecution(
    app, client, engine
):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("native MVCC evidence")
    owner, identity, path = await admitted(app, client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            legacy = await db.run_sync(lambda sync: feed.snapshot(sync, COMPANY, uuid.uuid4()))
    for _ in range(2):
        await build(engine, app.state.settings, TENANT, COMPANY, identity)
    result = SnapshotStatus.model_validate(await request(client, owner, "GET", path))
    assert result.status == "COMPLETE", result
    assert result.attempt == 1 and result.manifest.control == legacy.control
    assert result.manifest.facts_hash == legacy.facts_hash
    checksum, count, after = hashlib.sha256(), 0, 0
    while True:
        page = FactPage.model_validate(
            await request(
                client, owner, "GET", path + "/facts", {"after": str(after), "limit": "7"}
            )
        )
        for fact in page.items:
            checksum.update(canonical_json(fact.model_dump(mode="json")) + b"\n")
        count += len(page.items)
        if page.next_after is None:
            break
        assert page.next_after > after
        after = page.next_after
    assert count == result.completed_facts == legacy.fact_count
    assert checksum.hexdigest() == legacy.facts_hash


@pytest.mark.mysql
async def test_failed_read_view_publishes_failure_without_using_expired_orm_state(
    app, client, engine
):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("native MVCC rollback evidence")
    owner, identity, path = await admitted(app, client)
    app.state.settings.report_snapshot_fact_limit = 1
    await build(engine, app.state.settings, TENANT, COMPANY, identity)
    result = SnapshotStatus.model_validate(await request(client, owner, "GET", path))
    assert result.status == "FAILED" and result.manifest is None
    assert result.failure_code == "SNAPSHOT_CAPACITY_OR_VERIFICATION"
    with pytest.raises(httpx.HTTPStatusError) as error:
        await request(client, owner, "GET", path + "/facts")
    assert error.value.response.status_code == 409


async def test_snapshot_company_cycle_selects_only_eligible_scoped_attempts(
    app, engine, monkeypatch
):
    from accounting.tasks import reporting_snapshot as snapshots

    expected = {}
    scopes = ((TENANT, COMPANY), (TENANT, uuid.uuid4()), (uuid.uuid4(), COMPANY))
    for tenant, company in scopes:
        expected[tenant, company] = set()
        with tenant_scope(tenant):
            async with app.state.session_factory() as db, db.begin():
                for status, attempt, lease_offset, failure_code, eligible in (
                    ("QUEUED", 0, None, None, True),
                    ("FAILED", 2, None, None, True),
                    ("FAILED", 2, None, "SNAPSHOT_CAPACITY_OR_VERIFICATION", False),
                    ("FAILED", 3, None, None, False),
                    ("RUNNING", 1, -1, None, True),
                    ("RUNNING", 3, -1, None, True),
                    ("RUNNING", 1, 60, None, False),
                    ("COMPLETE", 1, None, None, False),
                ):
                    identity = uuid.uuid4()
                    db.add(
                        ReportSnapshotBuild(
                            id=identity,
                            tenant_id=tenant,
                            company_id=company,
                            status=status,
                            attempt=attempt,
                            failure_code=failure_code,
                            lease_until=None
                            if lease_offset is None
                            else utcnow() + dt.timedelta(seconds=lease_offset),
                        )
                    )
                    if eligible:
                        expected[tenant, company].add(identity)
    observed = {scope: set() for scope in scopes}

    async def record_build(_engine, _settings, tenant, company, identity):
        observed[tenant, company].add(identity)
        await asyncio.sleep(0)

    monkeypatch.setattr(snapshots, "build", record_build)
    await asyncio.gather(
        *(
            snapshots.cycle_company(
                engine, app.state.session_factory, app.state.settings, tenant, company
            )
            for tenant, company in scopes
        )
    )
    assert observed == expected


async def test_expired_final_snapshot_attempt_becomes_failed(app, client, engine):
    owner, identity, path = await admitted(app, client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await get(db, COMPANY, identity)
            row.status, row.attempt = "RUNNING", 3
            row.lease_until = utcnow() - dt.timedelta(seconds=1)
    for _ in range(2):
        await build(engine, app.state.settings, TENANT, COMPANY, identity)
    result = SnapshotStatus.model_validate(await request(client, owner, "GET", path))
    assert result.status == "FAILED" and result.failure_code == "ATTEMPTS_EXHAUSTED"
    assert result.attempt == 3 and result.manifest is None
