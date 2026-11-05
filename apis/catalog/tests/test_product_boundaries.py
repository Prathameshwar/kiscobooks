import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    Brand,
    BrandSeries,
    CatalogPolicyState,
    Item,
    Outbox,
    ProductFamily,
    ProductTypeRevision,
    UnitOfMeasure,
)
from tests.product_factories import setup_product
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy


async def test_draft_product_references_fail_closed(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, body = await setup_product(factory, tenant_a)
    path = f"/v1/companies/{company}/product-families"
    revision_id = uuid.UUID(body["product_type_revision_id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, revision_id)
            assert revision is not None
            published = revision.published_at
            revision.published_at = None
    response = await client.post(path, headers=command_headers(current), json=body)
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, revision_id)
            assert revision is not None
            revision.published_at = published
            unit = await db.get(UnitOfMeasure, uuid.UUID(body["default_item"]["base_unit_id"]))
            assert unit is not None
            unit.is_active = False
    response = await client.post(path, headers=command_headers(current), json=body)
    assert response.status_code == 409, response.text
    await policy(factory, tenant_a, company, user, "catalog.unit_of_measure", "is_active", "read")
    for unit_id in (body["default_item"]["base_unit_id"], str(uuid7())):
        response = await client.post(
            path,
            headers=command_headers(current),
            json={**body, "default_item": {**body["default_item"], "base_unit_id": unit_id}},
        )
        assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0
            assert (
                await db.scalar(select(func.count(Outbox.id)).where(Outbox.tenant_id == tenant_a))
                == 0
            )


async def test_draft_product_rejects_inactive_and_wrong_brand_series(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current, body = await setup_product(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            common = {"tenant_id": tenant_a, "company_id": company}
            first = Brand(id=uuid7(), code="FIRST", name="First", is_active=False, **common)
            second = Brand(id=uuid7(), code="SECOND", name="Second", **common)
            db.add_all([first, second])
            await db.flush()
            series = BrandSeries(
                id=uuid7(),
                code="SERIES",
                name="Series",
                brand_id=second.id,
                is_active=False,
                **common,
            )
            db.add(series)
            await db.flush()
            first_id, second_id, series_id = first.id, second.id, series.id
    path = f"/v1/companies/{company}/product-families"
    for changes, status in (
        ({"brand_id": str(first_id)}, 409),
        ({"brand_id": str(second_id), "series_id": str(series_id)}, 409),
    ):
        result = await client.post(path, headers=command_headers(current), json={**body, **changes})
        assert result.status_code == status, result.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            stored_brand = await db.get(Brand, first_id)
            assert stored_brand is not None
            stored_brand.is_active = True
    result = await client.post(
        path,
        headers=command_headers(current),
        json={**body, "brand_id": str(first_id), "series_id": str(series_id)},
    )
    assert result.status_code == 403, result.text
    # Creation requires the pair; draft PATCH revalidates the merged values too.
    result = await client.post(
        path, headers=command_headers(current), json={**body, "series_id": str(series_id)}
    )
    assert result.status_code == 422, result.text
    created = await client.post(path, headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    result = await client.patch(
        path + "/" + created.json()["family"]["id"],
        headers=command_headers(current),
        json={"expected_version": 1, "series_id": str(series_id)},
    )
    assert result.status_code == 409, result.text


async def test_product_version_exhaustion_and_non_draft_boundaries(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current, body = await setup_product(factory, tenant_a)
    path = f"/v1/companies/{company}"
    created = await client.post(
        path + "/product-families", headers=command_headers(current), json=body
    )
    assert created.status_code == 201, created.text
    family_id = uuid.UUID(created.json()["family"]["id"])
    item_id = uuid.UUID(created.json()["default_item"]["id"])
    family_path = path + "/product-families/" + str(family_id)
    item_path = path + "/items/" + str(item_id)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, family_id)
            assert family is not None
            family.row_version = 2**31 - 1
    response = await client.patch(
        family_path,
        headers=command_headers(current),
        json={"expected_version": 2**31 - 1, "name": "Overflow"},
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, family_id)
            assert family is not None
            family.row_version = 1
            state = await db.scalar(
                select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
            )
            assert state is not None
            state.generation = 2**63 - 1
    response = await client.patch(
        item_path,
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Overflow"},
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, family_id)
            assert family is not None
            family.status = "ACTIVE"
    for route in (family_path, item_path):
        response = await client.patch(
            route,
            headers=command_headers(current),
            json={"expected_version": 1, "name": "Non-draft"},
        )
        assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, item_id)
            assert item is not None
            item.status = "ACTIVE"
    response = await client.patch(
        item_path,
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Non-draft"},
    )
    assert response.status_code == 409, response.text


async def test_optional_product_quantity_can_be_cleared(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current, body = await setup_product(factory, tenant_a)
    prefix = f"/v1/companies/{company}"
    created = await client.post(
        prefix + "/product-families", headers=command_headers(current), json=body
    )
    assert created.status_code == 201, created.text
    item_path = prefix + "/items/" + created.json()["default_item"]["id"]
    cleared = await client.patch(
        item_path,
        headers=command_headers(current),
        json={"expected_version": 1, "min_sale_quantity": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["min_sale_quantity"] is None and cleared.json()["row_version"] == 2
    family_path = prefix + "/product-families/" + created.json()["family"]["id"]
    invalid = await client.patch(
        family_path, headers=command_headers(current), json={"expected_version": 1, "name": None}
    )
    assert invalid.status_code == 422, invalid.text


async def test_foreign_product_patch_reference_is_scope_error_before_database_flush(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current, body = await setup_product(factory, tenant_a)
    foreign_company, _, _, _ = await setup_product(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            brand = Brand(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=foreign_company,
                code="FOREIGN",
                name="Foreign",
            )
            db.add(brand)
            await db.flush()
            foreign_id = brand.id
    route = f"/v1/companies/{company}/product-families"
    created = await client.post(route, headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    result = await client.patch(
        route + "/" + created.json()["family"]["id"],
        headers=command_headers(current),
        json={"expected_version": 1, "brand_id": str(foreign_id)},
    )
    assert result.status_code == 403, result.text
