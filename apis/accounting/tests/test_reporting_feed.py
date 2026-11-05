import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from reporting_contract.contract import FactPage, Manifest
from reporting_contract.transport import Owner, request
from sqlalchemy import func, select

from accounting.models.masters import Account, AccountingSetup
from accounting.models.reporting import (
    ReportChange,
    ReportChangeFact,
    ReportSnapshot,
    ReportSnapshotFact,
)
from accounting.tasks.reporting_feed import head, snapshot
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import fiscal_setup


async def test_setup_only_counter_changes_preserve_report_generation(client, app):
    await fiscal_setup(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            prior = await db.run_sync(lambda sync: head(sync, COMPANY))
            previous = Manifest.model_validate(prior.manifest)
        async with app.state.session_factory() as db, db.begin():
            setup = await db.scalar(select(AccountingSetup))
            setup.generation += 1
        async with app.state.session_factory() as db, db.begin():
            current = await db.run_sync(lambda sync: snapshot(sync, COMPANY, uuid.uuid4()))
            assert current.sequence == previous.sequence
            assert current.control == previous.control
            assert current.generation == previous.generation


async def test_source_changes_keep_the_sealed_report_lineage(client, app):
    await fiscal_setup(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            frozen = await db.run_sync(lambda sync: snapshot(sync, COMPANY, uuid.uuid4()))
        async with app.state.session_factory() as db, db.begin():
            setup = await db.scalar(select(AccountingSetup))
            setup.generation += 1
            account = await db.scalar(select(Account).limit(1))
            account.name = "Reviewed name after source snapshot"
            account.row_version += 1
        async with app.state.session_factory() as db:
            latest = await db.run_sync(lambda sync: head(sync, COMPANY))
            changed = Manifest.model_validate(latest.manifest)
            assert changed.sequence == frozen.sequence + 1
            assert changed.generation == frozen.generation


async def test_frozen_signed_snapshot_and_complete_commit_capture(client, app):
    await fiscal_setup(client)
    secret = SecretStr(secrets.token_hex(32))
    key = "reports.test"
    app.state.settings.report_credentials[key] = SnapshotCredential(
        secret=secret, scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),)
    )
    owner = Owner(
        origin="http://127.0.0.1",
        key_id=key,
        secret=secret,
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    base = f"/internal/v1/reporting/{TENANT}/{COMPANY}"
    identity = uuid.uuid4()
    frozen = Manifest.model_validate(
        await request(client, owner, "POST", base + f"/snapshots/{identity}")
    )
    assert frozen.fact_count > 40
    pages = FactPage.model_validate(
        await request(client, owner, "GET", base + f"/snapshots/{identity}/facts", {"limit": "200"})
    )
    assert len(pages.items) == frozen.fact_count
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            account = await db.scalar(select(Account).limit(1))
            source_id = account.id
            account.name = "Revised after snapshot"
            account.row_version += 1
    latest = await request(client, owner, "GET", base + "/head")
    assert latest["sequence"] == frozen.sequence + 1
    changed = Manifest.model_validate(
        await request(client, owner, "GET", base + f'/changes/{latest["sequence"]}')
    )
    page = FactPage.model_validate(
        await request(client, owner, "GET", base + f"/changes/{changed.id}/facts")
    )
    assert len(page.items) == 1 and page.items[0].source_id == source_id
    assert page.items[0].data["name"] == "Revised after snapshot"
    frozen_again = await request(client, owner, "POST", base + f"/snapshots/{identity}")
    assert frozen_again == frozen.model_dump(mode="json")
    unchanged = await request(client, owner, "GET", base + f"/snapshots/{identity}/facts")
    assert unchanged == pages.model_dump(mode="json")
    assert (await client.get(base + "/head")).status_code == 401
    with pytest.raises(httpx.HTTPStatusError):
        await request(client, owner, "GET", base.replace(str(COMPANY), str(uuid.uuid4())) + "/head")


async def test_transaction_and_savepoint_rollback_never_publish_changed_values(client, app):
    await fiscal_setup(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            before = (await db.run_sync(lambda sync: head(sync, COMPANY))).sequence
        with pytest.raises(RuntimeError):
            async with app.state.session_factory() as db, db.begin():
                account = await db.scalar(select(Account).limit(1))
                account.name = "Never committed"
                await db.flush()
                raise RuntimeError("rollback")
        async with app.state.session_factory() as db, db.begin():
            account = await db.scalar(select(Account).limit(1))
            original = account.name
            with pytest.raises(RuntimeError):
                async with db.begin_nested():
                    account.name = "Rolled back savepoint"
                    await db.flush()
                    raise RuntimeError("rollback nested")
            # An outer unrelated change commits; collected keys must be re-read from final state.
            await db.refresh(account)
            account.row_version += 1
        async with app.state.session_factory() as db:
            latest = await db.run_sync(lambda sync: head(sync, COMPANY))
            assert latest.sequence == before + 1
            row = await db.scalar(
                select(ReportChangeFact).where(ReportChangeFact.change_id == latest.id)
            )
            assert row.fact["data"]["name"] == original


async def test_owner_export_isolation_and_immutability(client, app):
    await fiscal_setup(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            result = await db.run_sync(lambda sync: snapshot(sync, COMPANY, uuid.uuid4()))
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                row = await db.get(ReportSnapshot, result.id)
                row.manifest = {}
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            for model in (ReportChange, ReportChangeFact, ReportSnapshot, ReportSnapshotFact):
                assert await db.scalar(select(func.count(model.id))) == 0


@pytest.mark.mysql
async def test_snapshot_fence_blocks_concurrent_commit_without_losing_change(client, app, engine):
    import asyncio

    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("requires native commit fencing")
    await fiscal_setup(client)
    entered = asyncio.Event()

    async def writer():
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db, db.begin():
                account = await db.scalar(select(Account).limit(1))
                identity = account.id
                account.name = "Committed after barrier"
                account.row_version += 1
                await db.flush()
                entered.set()
            return identity

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            frozen = await db.run_sync(lambda sync: snapshot(sync, COMPANY, uuid.uuid4()))
            pending = asyncio.create_task(writer())
            await asyncio.wait_for(entered.wait(), 10)
            await asyncio.sleep(0.05)
            assert not pending.done()
        identity = await asyncio.wait_for(pending, 10)
        async with app.state.session_factory() as db:
            latest = await db.run_sync(lambda sync: head(sync, COMPANY))
            assert latest.sequence == frozen.sequence + 1
            exported = await db.scalar(
                select(ReportChangeFact).where(ReportChangeFact.change_id == latest.id)
            )
            assert exported.fact["source_id"] == str(identity)
            assert exported.fact["data"]["name"] == "Committed after barrier"
            old = list(
                await db.scalars(
                    select(ReportSnapshotFact).where(ReportSnapshotFact.snapshot_id == frozen.id)
                )
            )
            assert all(row.fact["data"].get("name") != "Committed after barrier" for row in old)


async def test_committed_execution_receipts_are_present_in_financial_export(client, app):
    from accounting.tasks.reporting_feed import controls
    from tests.test_fiscal_api import change
    from tests.test_voucher_execution import command, run

    periods = await fiscal_setup(client)
    opened = (await change(client, periods[0], "OPEN")).json()
    result = await run(app, command(opened))
    assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            proof = await db.run_sync(lambda sync: snapshot(sync, COMPANY, uuid.uuid4()))
            counted = await db.run_sync(lambda sync: controls(sync, COMPANY))
            await db.flush()
            rows = list(
                await db.scalars(
                    select(ReportSnapshotFact).where(ReportSnapshotFact.snapshot_id == proof.id)
                )
            )
            receipts = [row.fact for row in rows if row.fact["entity"] == "voucher_execution"]
            assert counted.counts["voucher_execution"] == len(receipts) == 1
            assert receipts[0]["data"]["result"]["outcome"] == "COMMITTED"
