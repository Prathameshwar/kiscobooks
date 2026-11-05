import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, UnitOfMeasure
from catalog.models.bulk import BulkChangeSetEffect, BulkJobRecord
from tests.bulk_factories import post, run, setup, unit_row

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_bulk_preview_rolls_back_then_commit_is_sealed_and_replayable(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    body = {"format": "JSON", "records": [unit_row("ea"), unit_row("box")]}
    request = {**auth, "Idempotency-Key": str(uuid7())}
    staged = await client.post(root, headers=request, json=body)
    assert staged.status_code == 202, staged.text
    job = staged.json()
    replay = await client.post(root, headers=request, json=body)
    assert replay.status_code == 202 and replay.json()["id"] == job["id"]
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0
            assert (
                await db.scalar(
                    select(func.count(IdempotencyKey.id)).where(
                        IdempotencyKey.endpoint == "catalog.unit_of_measure.create"
                    )
                )
                == 0
            )
    reviewed = (await client.get(root + "/" + job["id"], headers=auth)).json()
    listed = await client.get(
        root + "/" + job["id"] + "/records", headers=auth, params={"limit": 1}
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["page"]["has_more"]
    first = listed.json()["items"][0]
    preview = await client.get(root + "/" + job["id"] + "/records/" + first["id"], headers=auth)
    assert preview.status_code == 200 and preview.json()["before"] is None, preview.text
    assert preview.json()["after"]["quantity_increment"] == "1.0000"
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {
            "expected_version": reviewed["row_version"],
            "selection_digest": reviewed["selection_digest"],
        },
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 2
            assert await db.scalar(select(func.count(BulkChangeSetEffect.id))) == 2
            assert set(await db.scalars(select(BulkJobRecord.state))) == {"APPLIED"}


async def test_bulk_invalid_aggregate_has_no_partial_domain_effect(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    bad = unit_row("bad", group="aggregate")
    bad["data"]["quantity_increment"] = "not-a-number"
    job = await post(
        client,
        root,
        auth,
        "",
        {"format": "JSON", "records": [unit_row("ea", group="aggregate"), bad, unit_row("good")]},
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"
    failed = (await client.get(root + "/" + job["id"], headers=auth)).json()
    assert failed["invalid_count"] == 2
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/validate",
        {"expected_version": failed["row_version"], "selected_keys": ["good"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    reviewed = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {
            "expected_version": reviewed["row_version"],
            "selection_digest": reviewed["selection_digest"],
        },
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "PARTIAL"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(await db.scalars(select(UnitOfMeasure.code))) == ["GOOD"]
    completed = (await client.get(root + "/" + job["id"], headers=auth)).json()
    assert completed["state"] == "PARTIAL" and completed["completed_count"] == 1
