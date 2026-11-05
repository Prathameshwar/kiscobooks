import datetime as dt
import secrets
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.delivery import publish_batch
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT
from pydantic import SecretStr
from reporting_contract.authority import AuthoritySource
from sqlalchemy import func, select
from test_framework_execution import accepted

from reports.models.framework import ReportJob, ReportJobAttempt
from reports.tasks import framework_jobs as jobs
from reports.tasks.common import get
from reports.tasks.job_dispatcher import repair


def configured(app):
    app.state.settings.authority_sources = (
        AuthoritySource(
            origin="http://127.0.0.1",
            key_id="test.reports",
            secret=SecretStr(secrets.token_hex(32)),
            scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
        ),
    )
    return app.state.settings


async def test_repair_redelivers_lost_dispatch_and_does_not_duplicate_pending_outbox(
    app, client, prefix
):
    _, created = await accepted(app, client, prefix)
    settings, identity = configured(app), uuid.UUID(created["id"])
    factory = app.state.session_factory
    assert await repair(factory, settings) == 0
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            message = await db.scalar(
                select(Outbox).where(
                    Outbox.aggregate_id == identity, Outbox.event_type.in_(jobs.JOB_EVENTS)
                )
            )
            message.published_at = message.occurred_at = utcnow() - dt.timedelta(seconds=20)
    assert await repair(factory, settings) == 1
    assert await repair(factory, settings) == 0
    with tenant_scope(TENANT):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.aggregate_id == identity, Outbox.event_type.in_(jobs.JOB_EVENTS)
                    )
                )
                == 2
            )


async def test_repair_retries_dependency_failure_and_exhaustion_is_bounded(app, client, prefix):
    _, created = await accepted(app, client, prefix)
    settings, identity = configured(app), uuid.UUID(created["id"])
    factory = app.state.session_factory
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            await jobs.claim(db, COMPANY, identity)
            await jobs.fail(db, COMPANY, identity, 1, "DEPENDENCY_UNAVAILABLE")
    assert await repair(factory, settings) == 1
    assert await repair(factory, settings) == 0
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            row = await get(db, COMPANY, ReportJob, identity, lock=True)
            assert row.status == "QUEUED" and row.available_at > utcnow()
            row.available_at = utcnow() - dt.timedelta(seconds=1)
        for attempt in (2, 3):
            async with factory() as db, db.begin():
                assert (await jobs.claim(db, COMPANY, identity)).attempt == attempt
            async with factory() as db, db.begin():
                row = await get(db, COMPANY, ReportJob, identity, lock=True)
                row.lease_until = utcnow() - dt.timedelta(seconds=1)
        async with factory() as db, db.begin():
            assert await jobs.claim(db, COMPANY, identity) is None
        async with factory() as db:
            row = await get(db, COMPANY, ReportJob, identity)
            assert row.status == "FAILED" and row.failure_code == "ATTEMPTS_EXHAUSTED"
            attempts = list(await db.scalars(select(ReportJobAttempt)))
            assert len(attempts) == 3 and all(item.finished_at for item in attempts)
    assert await repair(factory, settings) == 0


async def test_rolled_back_claim_has_no_attempt_or_audit_and_broker_failure_is_recoverable(
    app, client, prefix
):
    _, created = await accepted(app, client, prefix)
    identity, factory = uuid.UUID(created["id"]), app.state.session_factory
    with tenant_scope(TENANT):
        async with factory() as db:
            baseline = await db.scalar(select(func.count(Outbox.id)))
        with pytest.raises(RuntimeError, match="rollback"):
            async with factory() as db, db.begin():
                await jobs.claim(db, COMPANY, identity)
                raise RuntimeError("rollback")
        async with factory() as db:
            assert (await get(db, COMPANY, ReportJob, identity)).status == "QUEUED"
            assert await db.scalar(select(func.count(ReportJobAttempt.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == baseline

    async def unavailable(message):
        raise OSError("broker unavailable")

    result = await publish_batch(factory, unavailable, event_types=jobs.JOB_EVENTS)
    assert result.confirmed == 0 and result.deferred == 1
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            row = await db.scalar(select(Outbox).where(Outbox.event_type.in_(jobs.JOB_EVENTS)))
            assert row.published_at is None and row.attempt_count == 1
            row.available_at = utcnow() - dt.timedelta(seconds=1)

    async def available(message):
        return True

    result = await publish_batch(factory, available, event_types=jobs.JOB_EVENTS)
    assert result.confirmed == 1 and result.deferred == 0
