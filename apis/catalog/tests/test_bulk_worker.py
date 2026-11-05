import asyncio
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import BulkJob, BulkJobRecord
from catalog.tasks import bulk_worker
from catalog.tasks.identity_source import IdentitySourceSettings, IdentitySourceUnavailableError
from tests.bulk_factories import post, proofs, setup, unit_row
from tests.conftest import ACTOR_SECRET

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def config(tenant: uuid.UUID, company: uuid.UUID) -> bulk_worker.BulkWorkerSettings:
    return bulk_worker.BulkWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=IdentitySourceSettings(
            base_url="http://127.0.0.1:1",
            request_secret=SecretStr(ACTOR_SECRET),
            response_secrets={"current": SecretStr(ACTOR_SECRET)},
        ),
        actor_signing_secret=SecretStr(ACTOR_SECRET),
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
        bulk_chunk_seconds=1,
    )


async def test_slow_chunks_stop_durably_instead_of_retrying_forever(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )

    async def proof(*args: Any, **kwargs: Any) -> Any:
        return next(
            p for p in proofs(tenant_a, company, user) if p.permissions == kwargs["permissions"]
        )

    async def slow(*args: Any, **kwargs: Any) -> bool:
        await asyncio.sleep(2)
        return True

    monkeypatch.setattr(bulk_worker, "fetch_actor_authorization", proof)
    monkeypatch.setattr(bulk_worker, "step", slow)
    assert await bulk_worker.run_once(factory, config(tenant_a, company), {}) == 0
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(BulkJob.state)) == "FAILED"
            row = (await db.scalars(select(BulkJobRecord))).one()
            assert row.state == "BLOCKED" and row.error_code == "chunk_timeout"


async def test_supervisor_retries_database_outage_and_disposes_on_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def failing(*args: Any, **kwargs: Any) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("test database outage")
        raise asyncio.CancelledError

    monkeypatch.setattr(bulk_worker, "run_once", failing)
    with pytest.raises(asyncio.CancelledError):
        await bulk_worker.serve(config(uuid.uuid4(), uuid.uuid4()))
    assert attempts == 2


@pytest.mark.parametrize("failure", ["network", "permission", "source", "expired"])
async def test_worker_failure_classification_preserves_or_stops_the_checkpoint(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    import datetime as dt

    from billing_platform.db.types import utcnow
    from billing_platform.errors import PermissionDeniedError

    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    issued = proofs(tenant_a, company, user)

    async def proof(*args: Any, **kwargs: Any) -> Any:
        if failure == "network":
            raise OSError("simulated transient owner failure")
        if failure == "permission":
            raise PermissionDeniedError("revoked")
        return next(p for p in issued if p.permissions == kwargs["permissions"])

    async def source_failure(*args: Any, **kwargs: Any) -> bool:
        if failure == "expired":
            monkeypatch.setattr(bulk_worker, "utcnow", lambda: utcnow() + dt.timedelta(seconds=31))
        raise IdentitySourceUnavailableError("test source changed")

    monkeypatch.setattr(bulk_worker, "fetch_actor_authorization", proof)
    monkeypatch.setattr(bulk_worker, "step", source_failure)
    cursors = {(tenant_a, company): uuid.UUID(job["id"])}
    assert await bulk_worker.run_once(factory, config(tenant_a, company), cursors) == 0
    with tenant_scope(tenant_a):
        async with factory() as db:
            stored = (await db.scalars(select(BulkJob))).one()
            assert stored.state == (
                "FAILED" if failure in {"permission", "expired"} else "VALIDATING"
            )
            version = stored.row_version
    subscription = config(tenant_a, company).source_subscriptions[0]
    await bulk_worker.stop_job(factory, subscription, uuid.UUID(job["id"]), version + 1)
    await bulk_worker.stop_job(factory, subscription, uuid.uuid4(), version)
    if failure in {"permission", "expired"}:
        await bulk_worker.stop_job(factory, subscription, uuid.UUID(job["id"]), version)
        assert await bulk_worker.run_once(factory, config(tenant_a, company), cursors) == 0
        assert not cursors


async def test_successful_worker_reuses_cursor_without_idle_sleep_and_cleans_completed_effects(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datetime as dt

    from billing_platform.db.types import utcnow

    from catalog.models.bulk import BulkChangeSetEffect, BulkImportArtifact
    from tests.test_bulk_products_prices import reviewed_commit

    company, user, auth = await setup(factory, tenant_a)
    job_id = await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {"format": "JSON", "records": [unit_row("ea")]},
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            artifact = (await db.scalars(select(BulkImportArtifact))).one()
            artifact.expires_at = utcnow() - dt.timedelta(days=1)
    assert (
        await bulk_worker.expire_artifacts(
            factory, config(tenant_a, company).source_subscriptions[0]
        )
        == 1
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            effect = (await db.scalars(select(BulkChangeSetEffect))).one()
            assert effect.results == {} and effect.source_pins == []
            job = await db.get(BulkJob, uuid.UUID(job_id))
            assert job is not None and job.state == "SUCCEEDED"
    attempts = iter((1, 0))
    sleeps = []

    async def work(*args: Any, **kwargs: Any) -> int:
        try:
            return next(attempts)
        except StopIteration:
            raise asyncio.CancelledError from None

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(bulk_worker, "run_once", work)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await bulk_worker.serve(config(tenant_a, company))
    assert sleeps == [2]


def test_worker_entrypoint_loads_scoped_settings_and_runs_the_supervisor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import runpy
    from collections.abc import Coroutine

    settings = config(uuid.uuid4(), uuid.uuid4())
    monkeypatch.setenv("CATALOG_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("CATALOG_ACTOR_SIGNING_SECRET", ACTOR_SECRET)
    monkeypatch.setenv(
        "CATALOG_IDENTITY_SOURCE",
        json.dumps(
            {
                "base_url": "http://127.0.0.1:1",
                "request_secret": ACTOR_SECRET,
                "response_secrets": {"current": ACTOR_SECRET},
            }
        ),
    )
    monkeypatch.setenv(
        "CATALOG_SOURCE_SUBSCRIPTIONS",
        json.dumps([x.model_dump(mode="json") for x in settings.source_subscriptions]),
    )
    started = []

    def run(coroutine: Coroutine[Any, Any, Any]) -> None:
        started.append(True)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", run)
    runpy.run_module("catalog.tasks.bulk_worker", run_name="__main__")
    assert started == [True]


async def test_worker_advances_to_the_next_queued_job_in_the_same_poll_cycle(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    for code in ("ea", "box"):
        job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row(code)]})
        await post(
            client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
        )

    async def proof(*args: Any, **kwargs: Any) -> Any:
        return next(
            p for p in proofs(tenant_a, company, user) if p.permissions == kwargs["permissions"]
        )

    monkeypatch.setattr(bulk_worker, "fetch_actor_authorization", proof)
    settings = config(tenant_a, company).model_copy(update={"bulk_chunk_seconds": 25})
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    assert await bulk_worker.run_once(factory, settings, cursors) == 1
    first = cursors[tenant_a, company]
    assert await bulk_worker.run_once(factory, settings, cursors) == 1
    assert cursors[tenant_a, company] > first
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(await db.scalars(select(BulkJob.state))) == ["READY", "READY"]
