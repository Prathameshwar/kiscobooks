"""Real child processes must stop at their budget even under Celery's solo pool."""

import subprocess
import sys
import time
import uuid

import pytest
from celery.concurrency.solo import TaskPool
from pydantic import SecretStr

from reports.tasks.celery_app import TASK_NAME, application


def test_solo_worker_terminates_stalled_work_and_accepts_the_next_task(app, tmp_path, monkeypatch):
    from reports.tasks import job_process

    late = tmp_path / "late"
    original = subprocess.run
    attempts = []

    def child(command, **kwargs):
        attempts.append(kwargs)
        code = "import sys,time; from pathlib import Path; time.sleep(1); Path(sys.argv[1]).touch()"
        return original([command[0], "-c", code, str(late)], **kwargs)

    settings = app.state.settings.model_copy(
        update={"job_broker_url": SecretStr("amqp://localhost")}
    )
    worker = application(settings)
    task = worker.tasks[TASK_NAME]
    monkeypatch.setattr(job_process.subprocess, "run", child)
    monkeypatch.setattr(job_process, "lane_seconds", lambda settings, lane: 0.1)
    outcomes = []

    def run():
        try:
            task.run(*(str(uuid.uuid4()) for _ in range(3)))
        except RuntimeError as exc:
            outcomes.append(str(exc))

    try:
        TaskPool(1).apply_async(run, callback=lambda result: None)
        assert outcomes == ["report worker failed: TimeoutError"]
        assert attempts[0]["timeout"] == 0.1
        assert attempts[0]["shell"] is False
        if sys.platform == "win32":
            assert attempts[0]["creationflags"] == subprocess.CREATE_NO_WINDOW
        monkeypatch.setattr(job_process.subprocess, "run", original)
        # A real fast child can follow a killed child in the same solo lane.
        monkeypatch.setattr(job_process, "lane_seconds", lambda settings, lane: 5)
        with monkeypatch.context() as patch:
            patch.setattr(
                job_process,
                "command",
                lambda scope, seconds: [
                    sys._base_executable if sys.platform == "win32" else sys.executable,
                    "-c",
                    "pass",
                ],
            )
            task.run(*(str(uuid.uuid4()) for _ in range(3)))
        time.sleep(1.1)
        assert not late.exists()
    finally:
        worker.close()


def test_child_configuration_is_private_and_child_failures_are_sanitized(app, monkeypatch):
    import json

    from billing_platform.service_auth import CompanyServiceScope
    from reporting_contract.authority import AuthoritySource

    from reports.tasks import job_process

    app.state.settings.authority_sources = (
        AuthoritySource(
            origin="http://127.0.0.1:12345",
            key_id="test",
            secret=app.state.settings.actor_signing_secret,
            scopes=(CompanyServiceScope(tenant_id=uuid.uuid4(), company_id=uuid.uuid4()),),
        ),
    )

    calls = []

    def child(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr(job_process.subprocess, "run", child)
    with pytest.raises(RuntimeError, match="report child failed"):
        job_process.run(app.state.settings, (uuid.uuid4(), uuid.uuid4(), uuid.uuid4()), "SHORT")
    command, kwargs = calls[0]
    configuration = json.loads(kwargs["input"])
    secret = app.state.settings.actor_signing_secret.get_secret_value()
    assert configuration["actor_signing_secret"] == secret
    assert configuration["authority_sources"][0]["secret"] == secret
    from reports.config import Settings

    assert Settings.model_validate(configuration) == app.state.settings
    assert secret not in " ".join(command)
    assert "input" in kwargs
    if sys.platform == "win32":
        assert kwargs["env"]["__PYVENV_LAUNCHER__"] == sys.executable
    assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
    assert job_process.lane_seconds(app.state.settings, "SHORT") == 60
    assert (
        job_process.lane_seconds(app.state.settings, "BULK")
        == app.state.settings.export_timeout_seconds + 60
    )
    assert job_process.lane_seconds(app.state.settings, "RENDER") == 90
    with pytest.raises(KeyError):
        job_process.lane_seconds(app.state.settings, "unknown")


def test_child_watchdog_stops_executor_shutdown_after_revocation(app):
    from reports.tasks.job_process import command, configuration, environment

    # Invoke the actual entry point with a thread that never returns. Parent timeout
    # is only a test backstop; the child must exit with its own deadline category.
    code = """
import asyncio, os, sys, threading, types
from reports.tasks import job_child
async def stalled(*args):
    await asyncio.to_thread(threading.Event().wait)
framework_worker = types.ModuleType('reports.tasks.framework_worker')
framework_worker.execute = stalled
sys.modules[framework_worker.__name__] = framework_worker
os._exit(job_child.main())
"""
    result = subprocess.run(  # noqa: S603 -- fixed test code and generated UUID identities.
        [
            command((uuid.uuid4(), uuid.uuid4(), uuid.uuid4()), 2)[0],
            "-c",
            code,
            *(str(uuid.uuid4()) for _ in range(3)),
            "2",
        ],
        input=configuration(app.state.settings).encode(),
        env=environment(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert result.returncode == 124


def test_celery_uses_the_delivered_lane_budget_and_rejects_unknown_routes(app, monkeypatch):
    from reports.tasks import celery_app

    settings = app.state.settings.model_copy(
        update={"job_broker_url": SecretStr("amqp://localhost")}
    )
    worker = application(settings)
    calls = []
    monkeypatch.setattr(celery_app, "run", lambda settings, scope, lane: calls.append(lane))
    task = worker.tasks[TASK_NAME]
    try:
        for lane in ("short", "bulk", "render"):
            task.push_request(
                delivery_info={"routing_key": settings.job_queue_namespace + "." + lane}
            )
            try:
                task.run(*(str(uuid.uuid4()) for _ in range(3)))
            finally:
                task.pop_request()
        assert calls == ["SHORT", "BULK", "RENDER"]
        task.push_request(delivery_info={"routing_key": "untrusted.bulk"})
        try:
            with pytest.raises(RuntimeError, match="ValueError"):
                task.run(*(str(uuid.uuid4()) for _ in range(3)))
        finally:
            task.pop_request()
    finally:
        worker.close()


async def test_real_child_opens_native_database_and_respects_a_cancelled_job(app, client, prefix):
    import asyncio

    from conftest import COMPANY, TENANT, headers
    from test_framework_execution import accepted

    from reports.tasks.job_process import run

    if app.state.engine.dialect.name != "mysql":
        pytest.skip("real report child requires disposable native MySQL")
    path, created = await accepted(app, client, prefix)
    target = path + "/" + created["id"]
    cancelled = await client.post(target + "/cancel", headers=headers())
    assert cancelled.status_code == 200
    settings = app.state.settings.model_copy(
        update={
            "database_url": app.state.engine.url.render_as_string(hide_password=False),
        }
    )
    await asyncio.to_thread(run, settings, (TENANT, COMPANY, uuid.UUID(created["id"])), "SHORT")
    assert (await client.get(target, headers=headers())).json()["status"] == "CANCELLED"
