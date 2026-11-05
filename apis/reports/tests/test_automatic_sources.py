import asyncio
import datetime as dt
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import authorize_snapshot, response_headers
from conftest import COMPANY, TENANT, headers
from factories import build_readiness
from sqlalchemy import func, select
from test_source_worker import Source

from reports.models.core import ReportGeneration
from reports.models.readiness import ReportReadiness
from reports.models.source_versions import ReportGenerationRequest
from reports.tasks.automatic_sources import reconcile
from reports.tasks.source_worker import cycle
from tools.framework_data import manifest


async def test_slow_company_does_not_block_other_company_refreshes(app, monkeypatch):
    from billing_platform.service_auth import CompanyServiceScope

    from reports.tasks import enrollment, source_worker

    first = AutomaticSource().owner
    other = uuid.uuid4()
    second = first.model_copy(
        update={"scopes": (CompanyServiceScope(tenant_id=TENANT, company_id=other),)}
    )
    settings = app.state.settings.model_copy(
        update={"source_versions_enabled": True, "source_parallelism": 2}
    )
    original_sleep = asyncio.sleep
    fast_cycles = 0
    repeated = asyncio.Event()

    async def discover(*args):
        return (first, second)

    async def process(settings, *args):
        nonlocal fast_cycles
        if settings.owners[0].scopes[0].company_id == COMPANY:
            await asyncio.Event().wait()
        else:
            fast_cycles += 1
            if fast_cycles >= 3:
                repeated.set()

    async def brief_sleep(seconds):
        await original_sleep(0.001)

    monkeypatch.setattr(enrollment, "owners", discover)
    monkeypatch.setattr(source_worker, "cycle", process)
    monkeypatch.setattr(source_worker.asyncio, "sleep", brief_sleep)
    task = asyncio.create_task(source_worker.run(settings))
    try:
        await asyncio.wait_for(repeated.wait(), timeout=2)
        assert fast_cycles >= 3
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class AutomaticSource(Source):
    def __init__(self):
        super().__init__()
        self.waiting = False
        self.offline = False
        identity = uuid.uuid4()
        self.snapshots[identity] = manifest(10, tenant=TENANT, company=COMPANY, snapshot=identity)

    def response(self, incoming):
        if self.offline:
            return httpx.Response(503)
        if not incoming.url.path.endswith("/refresh-stock"):
            return super().response(incoming)
        credential, framed, key = authorize_snapshot(
            {self.owner.key_id: self.credential},
            owner="accounting",
            requester="reports",
            tenant_id=TENANT,
            company_id=COMPANY,
            headers=incoming.headers,
            method="POST",
            path=incoming.url.path,
            query="",
            body=b"",
        )
        body = canonical_json({"status": "READY"})
        return httpx.Response(
            200,
            content=body,
            headers=response_headers(
                credential,
                owner="accounting",
                requester="reports",
                key_id=key,
                request_bytes=framed,
                body=body,
            ),
        )


async def test_automatic_first_build_coalescing_freshness_and_outage(app, client):
    source = AutomaticSource()
    settings = app.state.settings
    settings.owners = (source.owner,)
    settings.source_versions_enabled = settings.automatic_sources_enabled = True
    factory = app.state.session_factory

    async def due():
        with tenant_scope(TENANT):
            async with factory.begin() as db:
                health = await db.scalar(select(ReportReadiness))
                health.next_attempt_at = utcnow() - dt.timedelta(seconds=1)

    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:
        await reconcile(factory, wire, source.owner, TENANT, COMPANY)
        await due()
        await reconcile(factory, wire, source.owner, TENANT, COMPANY)
        with tenant_scope(TENANT):
            async with factory() as db:
                assert await db.scalar(select(func.count(ReportGeneration.id))) == 1
        await cycle(settings, factory, wire)
        ready = await client.get(f"/v2/companies/{COMPANY}/source-readiness", headers=headers())
        assert ready.status_code == 200, ready.text
        assert ready.json()["state"] == "CURRENT"
        with tenant_scope(uuid.uuid4()):
            async with factory.begin() as db:
                assert await db.scalar(select(ReportReadiness)) is None
                from billing_platform.db.tenant_context import require_current_tenant

                db.add(build_readiness(require_current_tenant(), uuid.uuid4()))
        with tenant_scope(TENANT):
            async with factory() as db:
                assert await db.scalar(select(func.count(ReportReadiness.id))) == 1
        first = ready.json()["generation_id"]
        await due()
        await reconcile(factory, wire, source.owner, TENANT, COMPANY)
        with tenant_scope(TENANT):
            async with factory() as db:
                assert await db.scalar(select(func.count(ReportGeneration.id))) == 1
        source.advance()
        await due()
        await reconcile(factory, wire, source.owner, TENANT, COMPANY)
        updating = await client.get(f"/v2/companies/{COMPANY}/source-readiness", headers=headers())
        assert updating.json()["state"] == "UPDATING"
        assert updating.json()["generation_id"] == first
        with tenant_scope(TENANT):
            async with factory() as db:
                requests = list(
                    await db.scalars(
                        select(ReportGenerationRequest).order_by(ReportGenerationRequest.id)
                    )
                )
                assert [r.strategy for r in requests] == ["FRESH", "REFRESH"]
        await cycle(settings, factory, wire)
        source.offline = True
        await due()
        await reconcile(factory, wire, source.owner, TENANT, COMPANY)
        delayed = await client.get(f"/v2/companies/{COMPANY}/source-readiness", headers=headers())
        assert delayed.json()["state"] == "DELAYED"
        assert delayed.json()["generation_id"] != first
        settings.automatic_sources_enabled = False
        disabled = await client.get(f"/v2/companies/{COMPANY}/source-readiness", headers=headers())
        assert disabled.json()["state"] == "NEEDS_ACTION"
        assert disabled.json()["failure_code"] == "AUTOMATIC_PREPARATION_DISABLED"
        assert disabled.json()["generation_id"] == delayed.json()["generation_id"]
