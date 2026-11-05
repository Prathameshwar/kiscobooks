import datetime as dt
import uuid
from dataclasses import replace
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.service_auth import CompanyServiceScope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from catalog.models.bulk import BulkChangeSetEffect, BulkImportArtifact, BulkJob, BulkJobRecord
from catalog.tasks.bulk_execution import step
from catalog.tasks.bulk_registry import OPERATIONS, Runtime
from catalog.tasks.bulk_worker import expire_artifacts
from tests.bulk_factories import post, proofs, run, setup, unit_row
from tests.conftest import ACTOR_SECRET

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def review(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    auth: dict[str, str],
    body: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", body)
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant, company, user, job["id"]) == "READY"
    return root, (await client.get(root + "/" + job["id"], headers=auth)).json()


async def queue(
    client: httpx.AsyncClient, root: str, auth: dict[str, str], job: dict[str, Any]
) -> None:
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {"expected_version": job["row_version"], "selection_digest": job["selection_digest"]},
    )


async def test_cancel_and_revision_preserve_completed_effects(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    rows = [unit_row("ea"), unit_row("box")]
    root, job = await review(
        client, factory, tenant_a, company, user, auth, {"format": "JSON", "records": rows}
    )
    await queue(client, root, auth, job)
    await step(
        factory,
        proofs(tenant_a, company, user),
        tenant_a,
        company,
        user,
        uuid.UUID(job["id"]),
        ACTOR_SECRET.encode(),
    )
    current = (await client.get(root + "/" + job["id"], headers=auth)).json()
    assert current["completed_count"] == 1
    cancelled = await post(
        client, root, auth, f"/{job['id']}/cancel", {"expected_version": current["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "CANCELLED"
    changed = [unit_row("changed"), rows[1]]
    denied = await client.post(
        root + "/" + job["id"] + "/revise",
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": cancelled["row_version"], "batch": {"records": changed}},
    )
    assert denied.status_code == 409, denied.text
    altered = [unit_row("ea"), rows[1]]
    altered[0]["data"]["symbol"] = "different"
    sealed = await client.post(
        root + "/" + job["id"] + "/revise",
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": cancelled["row_version"], "batch": {"records": altered}},
    )
    assert sealed.status_code == 409, sealed.text
    revised = await post(
        client,
        root,
        auth,
        f"/{job['id']}/revise",
        {"expected_version": cancelled["row_version"], "batch": {"records": rows}},
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": revised["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    fresh = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await queue(client, root, auth, fresh)
    assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 2
            assert sorted(await db.scalars(select(BulkChangeSetEffect.accepted_revision))) == [1, 2]


@pytest.mark.parametrize(
    "crash", [False, True], ids=["atomic-business-failure", "crash-before-receipt"]
)
async def test_failed_commit_rolls_back_and_crash_retry_has_one_effect(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    crash: bool,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root, job = await review(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {"format": "JSON", "atomicity": "ATOMIC", "records": [unit_row("ea"), unit_row("box")]},
    )
    await queue(client, root, auth, job)
    native = OPERATIONS["unit_of_measure", "CREATE"]

    async def fail(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        result = await native.call(runtime, body, target, key)
        if body.code == "BOX":
            if crash:
                raise RuntimeError("simulated process failure after domain write")
            raise ConflictError("simulated validation race")
        return result

    monkeypatch.setitem(OPERATIONS, ("unit_of_measure", "CREATE"), replace(native, call=fail))
    if crash:
        with pytest.raises(RuntimeError, match="simulated process failure"):
            await step(
                factory,
                proofs(tenant_a, company, user),
                tenant_a,
                company,
                user,
                uuid.UUID(job["id"]),
                ACTOR_SECRET.encode(),
            )
    else:
        assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0
            assert await db.scalar(select(func.count(BulkChangeSetEffect.id))) == 0
            if not crash:
                invalid = await db.scalar(
                    select(BulkJobRecord).where(BulkJobRecord.logical_key == "box")
                )
                assert invalid is not None and invalid.state == "FAILED"
    if crash:
        monkeypatch.setitem(OPERATIONS, ("unit_of_measure", "CREATE"), native)
        assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
        with tenant_scope(tenant_a):
            async with factory() as db:
                assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 2
                assert await db.scalar(select(func.count(BulkChangeSetEffect.id))) == 2


async def test_expiry_erases_private_payloads_without_deleting_job_identity(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root, job = await review(
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
            stored = await db.get(BulkJob, uuid.UUID(job["id"]))
            artifact = await db.scalar(select(BulkImportArtifact))
            assert stored is not None and artifact is not None
            stored.expires_at = artifact.expires_at = utcnow() - dt.timedelta(days=1)
    assert (
        await expire_artifacts(factory, CompanyServiceScope(tenant_id=tenant_a, company_id=company))
        == 1
    )
    assert (
        await expire_artifacts(factory, CompanyServiceScope(tenant_id=tenant_a, company_id=company))
        == 0
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(BulkImportArtifact.content)) == b""
            assert await db.scalar(select(BulkJobRecord.normalized_input)) == {}
            assert await db.scalar(select(BulkJob.state)) == "FAILED"


@pytest.mark.parametrize("all_fail", [False, True])
async def test_continue_independent_reports_failed_dependencies_and_actual_commits(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    all_fail: bool,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    dependent = unit_row("dependent")
    dependent["depends_on"] = ["first"]
    root, job = await review(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "on_error": "CONTINUE_INDEPENDENT",
            "records": [unit_row("first"), dependent, unit_row("independent")],
        },
    )
    await queue(client, root, auth, job)
    native = OPERATIONS["unit_of_measure", "CREATE"]

    async def fail(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        result = await native.call(runtime, body, target, key)
        if all_fail or body.code == "FIRST":
            raise ConflictError("commit-time business conflict")
        return result

    monkeypatch.setitem(OPERATIONS, ("unit_of_measure", "CREATE"), replace(native, call=fail))
    assert await run(factory, tenant_a, company, user, job["id"]) == (
        "FAILED" if all_fail else "PARTIAL"
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            blocked = await db.scalar(
                select(BulkJobRecord).where(BulkJobRecord.logical_key == "dependent")
            )
            assert (
                blocked is not None
                and blocked.state == "BLOCKED"
                and blocked.error_code == "dependency_failed"
            )
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == (0 if all_fail else 1)
            assert await db.scalar(select(func.count(BulkChangeSetEffect.id))) == (
                0 if all_fail else 1
            )
