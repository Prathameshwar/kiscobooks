"""Attribute form read graph, lifecycle and field authorization."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily
from tests.test_api import headers
from tests.test_attribute_practical_review import setup_axis
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_form_labels_values_and_active_family_draft_permissions(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    root = f"/v1/companies/{company}"
    route = root + f"/items/{ids['item']}/attribute-form"
    result = await client.get(route, headers=auth)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["fields"][0]["option_label"] == "Blue"
    assert data["fields"][0]["allowed_options"][0]["label"] == "Blue"
    assert data["fields"][0]["value"]["option_id"] == str(ids["attribute_option"])
    assert data["can_create_variant"] and data["can_configure"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family
            family.status = "ACTIVE"
    metadata = await client.get(
        root + "/entities/catalog.item/field-set",
        headers=auth,
        params={"operation": "update", "object_id": str(ids["item"])},
    )
    assert metadata.status_code == 200, metadata.text
    assert next(f for f in metadata.json()["fields"] if f["key"] == "sellable")["writable"]
    changed = await client.patch(
        root + f"/items/{ids['item']}",
        headers=command_headers(auth),
        json={"expected_version": 1, "sellable": False},
    )
    assert changed.status_code == 200, changed.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assert item
            item.status = "ACTIVE"
    result = await client.get(route, headers=auth)
    assert result.status_code == 200, result.text
    assert not result.json()["fields"][0]["writable"]
    assert result.json()["fields"][0]["variant_writable"]


@pytest.mark.parametrize(
    "entity,field",
    [
        ("attribute_definition", "name"),
        ("attribute_option", "name"),
        ("item_attribute_value", "value_text"),
        ("family_attribute_option", "option_id"),
    ],
)
async def test_form_refuses_partial_protected_graph(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    entity: str,
    field: str,
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    await policy(factory, tenant_a, company, ids["actor_user"], "catalog." + entity, field, "read")
    result = await client.get(
        f"/v1/companies/{company}/items/{ids['item']}/attribute-form", headers=auth
    )
    assert result.status_code == 403, result.text


async def test_form_write_deny_and_unknown_owner(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    route = f"/v1/companies/{company}/items/{ids['item']}/attribute-form"
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.item_attribute_value",
        "value_text",
        "write",
    )
    result = await client.get(route, headers=auth)
    assert result.status_code == 200, result.text
    assert not result.json()["fields"][0]["writable"]
    assert not result.json()["fields"][0]["variant_writable"]
    assert not result.json()["can_create_variant"]
    denied = await client.get(
        route, headers=headers(company, tenant=tenant_a, user=ids["actor_user"], permission=[])
    )
    assert denied.status_code == 403, denied.text
    missing = await client.get(
        f"/v1/companies/{company}/items/{uuid.uuid4()}/attribute-form", headers=auth
    )
    assert missing.status_code == 404, missing.text


async def test_form_owner_does_not_cross_tenants(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    denied = await client.get(
        f"/v1/companies/{company}/items/{ids['item']}/attribute-form",
        headers=headers(company, tenant=tenant_b, user=ids["actor_user"], permission=[]),
    )
    assert denied.status_code in {403, 404}, denied.text
