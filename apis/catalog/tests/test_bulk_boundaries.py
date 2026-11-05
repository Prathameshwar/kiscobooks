import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from catalog.tasks.bulk_execution import step
from tests.bulk_factories import post, proofs, run, setup, unit_row
from tests.conftest import ACTOR_SECRET

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_unit_commands_advance_bulk_dependency_generation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models.classification import CatalogPolicyState

    company, _, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}"
    first = await post(client, root, auth, "/units", unit_row("ea")["data"], status=201)
    second = await post(client, root, auth, "/units", unit_row("box")["data"], status=201)
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(CatalogPolicyState.generation).where(
                        CatalogPolicyState.company_id == company
                    )
                )
                == 3
            )
    await post(
        client,
        root,
        auth,
        "/unit-conversions",
        {
            "from_unit_id": second["id"],
            "canonical_unit_id": second["id"],
            "numerator": 1,
            "denominator": 1,
        },
        status=201,
    )
    await post(
        client,
        root,
        auth,
        "/unit-conversions",
        {
            "from_unit_id": first["id"],
            "canonical_unit_id": second["id"],
            "numerator": 12,
            "denominator": 1,
        },
        status=201,
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(CatalogPolicyState.generation).where(
                        CatalogPolicyState.company_id == company
                    )
                )
                == 5
            )


async def test_duplicate_updates_in_one_set_are_rejected(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}"
    original = await post(client, root, auth, "/units", unit_row("ea")["data"], status=201)
    rows = [
        {
            "key": key,
            "change_set": "same",
            "resource": "unit_of_measure",
            "action": "UPDATE",
            "target": {"id": original["id"]},
            "data": {"name": key},
        }
        for key in ("first", "last")
    ]
    job = await post(
        client,
        root + "/bulk-jobs",
        auth,
        "",
        {"format": "JSON", "mode": "UPDATE_ONLY", "records": rows},
    )
    await post(
        client,
        root + "/bulk-jobs",
        auth,
        f"/{job['id']}/validate",
        {"expected_version": job["row_version"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"


async def test_revoked_actor_and_changed_identity_stop_before_effect(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    review = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {"expected_version": review["row_version"], "selection_digest": review["selection_digest"]},
    )
    with pytest.raises(PermissionDeniedError):
        await step(
            factory,
            proofs(tenant_a, company, user, denied=frozenset({"catalog.bulk.commit"})),
            tenant_a,
            company,
            user,
            uuid.UUID(job["id"]),
            ACTOR_SECRET.encode(),
        )
    from tests.test_unit_api import policy, seed_context

    await seed_context(
        factory, tenant_a, company, user, (policy(user, "name", "write"),), version=3
    )
    with pytest.raises(ConflictError):
        await step(
            factory,
            proofs(tenant_a, company, user, version=3),
            tenant_a,
            company,
            user,
            uuid.UUID(job["id"]),
            ACTOR_SECRET.encode(),
        )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(await db.scalars(select(UnitOfMeasure.id))) == []


async def test_bounded_upload_above_receipt_json_limit_is_staged(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth = await setup(factory, tenant_a)
    rows = [unit_row("u" + str(index)) for index in range(30)]
    for row in rows:
        row["data"]["custom_fields"] = {"cf_note": "x" * 40000}
    result = await client.post(
        f"/v1/companies/{company}/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"format": "JSON", "records": rows},
    )
    assert result.status_code == 202, result.text


async def test_symbolic_dependency_is_replayed_then_resolved_to_real_effect(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(
        client,
        root,
        auth,
        "",
        {
            "format": "JSON",
            "records": [
                unit_row("ea"),
                {
                    "key": "rename",
                    "change_set": "rename",
                    "resource": "unit_of_measure",
                    "action": "UPDATE",
                    "target": {"record": "ea"},
                    "data": {"name": "Each renamed"},
                },
            ],
        },
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    review = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {"expected_version": review["row_version"], "selection_digest": review["selection_digest"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            row = await db.scalar(select(UnitOfMeasure))
            assert row is not None and row.name == "Each renamed" and row.row_version == 2
