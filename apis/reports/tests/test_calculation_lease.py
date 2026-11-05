"""Slow small calculations must retain ownership before the first output batch."""

import asyncio
import datetime as dt
import threading
import uuid

import pytest
from billing_platform.db.types import utcnow
from conftest import COMPANY, TENANT, headers
from test_framework_execution import accepted, proof

from reports.models import framework as models
from reports.tasks import framework_jobs as jobs
from reports.tasks import framework_worker as worker
from reports.tasks.report_catalog import ReferenceAdapter


@pytest.mark.parametrize("phase", ["source", "calculation", "native"])
async def test_calculation_renews_lease_before_any_result_rows(
    app, client, prefix, monkeypatch, phase
):
    path, created = await accepted(app, client, prefix)
    now = [utcnow()]
    pulse = threading.Event()
    heartbeats = []
    original_heartbeat, original_load = jobs.heartbeat, worker.load
    original_execute = ReferenceAdapter.execute
    monkeypatch.setattr(jobs, "utcnow", lambda: now[0])
    monkeypatch.setattr(models, "utcnow", lambda: now[0])
    monkeypatch.setattr(worker, "PULSE_SECONDS", 0.01, raising=False)

    async def heartbeat(*args):
        await original_heartbeat(*args)
        heartbeats.append(now[0])
        pulse.set()

    monkeypatch.setattr(jobs, "heartbeat", heartbeat)

    def tick():
        # Advance beyond the original 60-second lease without real-time waiting or load.
        for _ in range(2):
            pulse.clear()
            now[0] += dt.timedelta(seconds=35)
            pulse.wait(2)

    async def load(*args, **kwargs):
        facts = await original_load(*args, **kwargs)
        await asyncio.to_thread(tick)
        return facts

    def calculate(self, *args):
        tick()
        return original_execute(self, *args)

    async def enabled(*args):
        return True

    async def native(db, job, maximum):
        generation = await worker.get(db, COMPANY, worker.ReportGeneration, job.generation_id)
        facts = await original_load(db, generation, maximum)
        manifest = worker.Manifest.model_validate(generation.manifest)
        await asyncio.to_thread(tick)
        return (
            worker.catalog()
            .resolve(job.definition["code"])
            .handler.execute(facts, job.generation_id, job.parameters, manifest.control)
        )

    if phase == "source":
        monkeypatch.setattr(worker, "load", load)
    elif phase == "calculation":
        monkeypatch.setattr(ReferenceAdapter, "execute", calculate)
    else:
        monkeypatch.setattr(worker.native_execution, "enabled", enabled)
        monkeypatch.setattr(worker.native_execution, "calculate", native)

    async def authority(job):
        return proof(job)

    await worker.process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    result = await client.get(path + "/" + created["id"], headers=headers())
    assert result.json()["status"] == "COMPLETE", (result.text, heartbeats)
    assert result.json()["attempt"] == 1
    assert len(heartbeats) >= 2


@pytest.mark.parametrize("failure", ["revoked", "cancelled"])
async def test_supervised_calculation_stops_publication_and_joins_work(
    app, client, prefix, monkeypatch, failure
):
    path, created = await accepted(app, client, prefix)
    release = asyncio.Event()
    finished = []
    calls = 0
    original_load = worker.load
    monkeypatch.setattr(worker, "PULSE_SECONDS", 0.01)

    async def load(*args, **kwargs):
        facts = await original_load(*args, **kwargs)
        await asyncio.wait_for(release.wait(), timeout=2)
        finished.append(True)
        return facts

    async def authority(job):
        nonlocal calls
        calls += 1
        if calls > 1:
            if failure == "cancelled":
                async with app.state.session_factory() as db, db.begin():
                    row = await worker.get(db, COMPANY, worker.ReportJob, job.id, lock=True)
                    await jobs.cancel(db, row)
            release.set()
        return proof(job, allowed=calls == 1 or failure != "revoked")

    monkeypatch.setattr(worker, "load", load)
    await worker.process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created["id"]),
        authority,
    )
    target = path + "/" + created["id"]
    result = (await client.get(target, headers=headers())).json()
    assert result["status"] == ("BLOCKED" if failure == "revoked" else "CANCELLED")
    assert result["result"] is None and result["completed_rows"] == 0
    assert finished == [True]
    assert (await client.get(target + "/rows", headers=headers())).status_code == 409
