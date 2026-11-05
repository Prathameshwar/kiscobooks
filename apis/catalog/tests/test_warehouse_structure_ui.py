import uuid

import httpx
from billing_platform.db import tenant_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import CatalogPolicyState
from tests.test_api import headers
from tests.test_warehouse_groups import GROUPING, assign, create_group, dated, denial
from tests.test_warehouse_storage import seed_locations
from tests.warehouse_factories import auth


async def test_structure_context_is_readonly_and_scoped(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid.uuid4(), uuid.uuid4()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    root = f"/v1/companies/{company}"
    for resource in ("groups", "bins"):
        response = await client.get(
            root + "/warehouse-structure?resource=" + resource, headers=current
        )
        assert response.status_code == 200, response.text
        assert response.json()["company_id"] == str(company)
        assert response.json()["policy_generation"] == 1
        assert len(response.json()["business_date"]) == 10
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(CatalogPolicyState.id)) is None
    denied = await auth(factory, tenant_a, company, user, permission=("item.read",), version=3)
    assert (
        await client.get(root + "/warehouse-structure?resource=groups", headers=denied)
    ).status_code == 403
    assert (
        await client.get(root + "/warehouse-structure?resource=unknown", headers=current)
    ).status_code == 422
    assert (
        await client.get(root + "/warehouse-structure?resource=groups&unused=1", headers=current)
    ).status_code == 422
    assert (await client.get(root + "/warehouse-structure?resource=groups")).status_code == 401


async def test_native_structure_controls_and_bin_identity(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid.uuid4(), uuid.uuid4()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    for entity, required in {
        "warehouse_group": {"code", "name", "is_active"},
        "warehouse_bin": {"code", "name", "warehouse_id", "is_active"},
        "warehouse_group_parent": {"group_id", "parent_group_id", "valid_from", "valid_to"},
        "warehouse_group_assignment": {"warehouse_id", "group_id", "valid_from", "valid_to"},
    }.items():
        response = await client.get(
            f"/v1/companies/{company}/entities/catalog.{entity}/field-set?operation=create",
            headers=current,
        )
        assert response.status_code == 200, response.text
        fields = {field["key"]: field for field in response.json()["fields"]}
        assert all(fields[key]["control"] for key in required)
    assert (
        await client.get(
            f"/v1/companies/{company}/entities/catalog.warehouse/field-set?operation=create",
            headers=current,
        )
    ).status_code == 200
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.warehouse_bin/field-set?operation=update",
        headers=current,
    )
    fields = {field["key"]: field for field in response.json()["fields"]}
    assert not fields["warehouse_id"]["writable"] and not fields["is_active"]["writable"]
    manager = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["warehouse_group.read", "warehouse_group.manage"],
    )
    parent_path = f"/v1/companies/{company}/entities/catalog.warehouse_group_parent/field-set"
    for operation, writable in (("create", True), ("update", False)):
        metadata = await client.get(parent_path + "?operation=" + operation, headers=manager)
        assert metadata.status_code == 200
        assert all(
            field["writable"] == writable
            for field in metadata.json()["fields"]
            if field["key"] in {"parent_group_id", "valid_from"}
        )


async def test_membership_history_preserves_dates_and_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid.uuid4(), uuid.uuid4()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    warehouse, _ = await seed_locations(factory, tenant_a, company)
    group = (await create_group(client, company, current, "REGION"))["id"]
    assert (
        await assign(client, company, current, str(warehouse), group, dated(1))
    ).status_code == 200
    path = f"/v1/companies/{company}/warehouses/{warehouse}/group-history"
    response = await client.get(path + "?limit=1", headers=current)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["group_id"] == group
    assert response.json()["items"][0]["valid_from"] == dated(1)
    denied = await auth(
        factory, tenant_a, company, user, permission=("warehouse_group.read",), version=3
    )
    assert (await client.get(path, headers=denied)).status_code == 403
    assert (
        await client.get(
            f"/v1/companies/{uuid.uuid4()}/warehouses/{warehouse}/group-history", headers=current
        )
    ).status_code in {403, 404}
    assert (await client.get(path + "?q=bad", headers=current)).status_code == 422


async def test_membership_history_paging_and_field_denies(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid.uuid4(), uuid.uuid4()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    warehouse, _ = await seed_locations(factory, tenant_a, company)
    first = (await create_group(client, company, current, "ONE"))["id"]
    second = (await create_group(client, company, current, "TWO"))["id"]
    assert (
        await assign(client, company, current, str(warehouse), first, dated(1))
    ).status_code == 200
    assert (
        await assign(client, company, current, str(warehouse), second, dated(2))
    ).status_code == 200
    path = f"/v1/companies/{company}/warehouses/{warehouse}/group-history"
    page = (await client.get(path + "?limit=1&sort=valid_from", headers=current)).json()
    assert page["items"][0]["group_id"] == first and page["page"]["has_more"]
    response = await client.get(
        path,
        params={"limit": 1, "sort": "valid_from", "cursor": page["page"]["next_cursor"]},
        headers=current,
    )
    assert response.status_code == 200 and response.json()["items"][0]["group_id"] == second
    assert not response.json()["page"]["has_more"]
    assert (await client.get(path + "?valid_at=" + dated(1), headers=current)).json()["items"][0][
        "group_id"
    ] == first
    hidden = await auth(
        factory,
        tenant_a,
        company,
        user,
        permission=GROUPING,
        version=3,
        extra=(
            denial(company, user, "catalog.warehouse_group_assignment", "group_id", "read"),
            denial(company, user, "catalog.warehouse_group_assignment", "valid_from", "read"),
        ),
    )
    response = await client.get(path, headers=hidden)
    assert response.status_code == 200
    assert all(
        "group_id" not in row and "valid_from" not in row for row in response.json()["items"]
    )
    assert (await client.get(path + "?valid_at=" + dated(1), headers=hidden)).status_code == 403
    assert (await client.get(path + "?sort=valid_from", headers=hidden)).status_code == 403
