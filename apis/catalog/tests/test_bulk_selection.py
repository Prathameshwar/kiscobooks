import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from tests.bulk_factories import post, run, setup, unit_row

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_filter_freezes_ids_before_later_matching_insert(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}"
    await post(client, root, auth, "/units", unit_row("first")["data"], status=201)
    job = await post(
        client,
        root,
        auth,
        "/bulk-jobs",
        {
            "format": "FILTER",
            "resource": "unit_of_measure",
            "filters": {"dimension": "COUNT"},
            "data": {"name": "Selected"},
        },
    )
    await post(client, root, auth, "/units", unit_row("later")["data"], status=201)
    await post(
        client,
        root,
        auth,
        f"/bulk-jobs/{job['id']}/validate",
        {"expected_version": job["row_version"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    review = (await client.get(root + "/bulk-jobs/" + job["id"], headers=auth)).json()
    assert review["record_count"] == 1 and review["kind"] == "UPDATE"
    await post(
        client,
        root,
        auth,
        f"/bulk-jobs/{job['id']}/commit",
        {"expected_version": review["row_version"], "selection_digest": review["selection_digest"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert dict(
                (await db.execute(select(UnitOfMeasure.code, UnitOfMeasure.name))).tuples().all()
            ) == {"FIRST": "Selected", "LATER": "later"}


async def test_filter_rejects_float_with_validation_envelope(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}"
    await post(client, root, auth, "/units", unit_row("ea")["data"], status=201)
    response = await client.post(
        root + "/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "format": "FILTER",
            "resource": "unit_of_measure",
            "all_rows": True,
            "data": {"quantity_increment": 0.5},
        },
    )
    assert response.status_code == 422, response.text


async def test_item_kind_filter_uses_the_company_family_and_its_field_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from billing_platform.permissions import CATALOG_PERMISSIONS

    from tests.product_factories import setup_product
    from tests.test_api import headers
    from tests.test_unit_api import policy, seed_context

    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    await post(client, root, auth, "/product-families", body, status=201)
    request = {
        "format": "FILTER",
        "resource": "item",
        "filters": {"kind": "GOODS"},
        "data": {"name": "Selected"},
    }
    response = await client.post(
        root + "/bulk-jobs", headers={**auth, "Idempotency-Key": str(uuid7())}, json=request
    )
    assert response.status_code == 202 and response.json()["record_count"] == 1, response.text
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        (policy(user, "kind", "read", entity="catalog.product_family"),),
        version=3,
    )
    denied = await client.post(
        root + "/bulk-jobs", headers={**auth, "Idempotency-Key": str(uuid7())}, json=request
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"filters": {"unknown": "x"}},
        {"all_rows": True, "data": {"expected_version": 1}},
        {"filters": {"is_active": "true"}},
        {"filters": {"dimension": "UNKNOWN"}},
        {"resource": "item", "filters": {"family_id": "not-a-uuid"}},
    ],
)
async def test_selection_refuses_invalid_or_implicit_scopes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    change: dict[str, object],
) -> None:
    company, _, auth = await setup(factory, tenant_a)
    response = await client.post(
        f"/v1/companies/{company}/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "format": "FILTER",
            "resource": "unit_of_measure",
            "data": {"name": "Changed"},
            **change,
        },
    )
    assert response.status_code == 422, response.text


async def test_filter_never_silently_truncates_an_oversized_company_selection(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from decimal import Decimal

    from catalog.models.bulk import BulkJob

    company, _, auth = await setup(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add_all(
                [
                    UnitOfMeasure(
                        tenant_id=tenant_a,
                        company_id=company,
                        code=f"U{i}",
                        name=f"Unit {i}",
                        symbol="u",
                        dimension="COUNT",
                        decimal_places=0,
                        quantity_increment=Decimal("1"),
                    )
                    for i in range(2001)
                ]
            )
    response = await client.post(
        f"/v1/companies/{company}/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "format": "FILTER",
            "resource": "unit_of_measure",
            "all_rows": True,
            "data": {"name": "Changed"},
        },
    )
    assert response.status_code == 422 and "2000 targets" in response.text, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(await db.scalars(select(BulkJob.id))) == []
