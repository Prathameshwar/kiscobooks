"""Regressions for scoped aggregate writes and recoverable product revisions."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from catalog.models import Brand, Item, Outbox, ProductFamily
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_simple_products import create_simple

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize(
    ("reference", "status"), [("missing", 404), ("wrong_company", 403), ("wrong_tenant", 404)]
)
async def test_simple_patch_validates_references_before_persisting(
    client, factory, tenant_a, tenant_b, reference, status
):
    company, _, auth, _, product = await create_simple(client, factory, tenant_a)
    brand_id = uuid7()
    if reference != "missing":
        brand_tenant = tenant_b if reference == "wrong_tenant" else tenant_a
        with tenant_scope(brand_tenant):
            async with factory.begin() as db:
                db.add(
                    Brand(
                        id=brand_id,
                        tenant_id=brand_tenant,
                        company_id=uuid7(),
                        code="FOREIGN",
                        name="Foreign brand",
                    )
                )
    route = f"/v1/companies/{company}/products/{product['id']}"
    with tenant_scope(tenant_a):
        async with factory() as db:
            audit_count = await db.scalar(select(func.count(Outbox.id)))
    response = await client.patch(
        route,
        headers=command_headers(auth),
        json={
            "revision": product["revision"],
            "authoring_version": 0,
            "brand_id": str(brand_id),
            "name": "Must roll back",
        },
    )
    assert response.status_code == status, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.get(Item, uuid.UUID(product["id"]))
            family = await db.get(ProductFamily, item.family_id)
            assert item.name == family.name == product["name"]
            assert item.row_version == family.row_version == 1
            assert family.brand_id is None
            assert await db.scalar(select(func.count(Outbox.id))) == audit_count
    corrected = await client.patch(
        route,
        headers=command_headers(auth),
        json={"revision": product["revision"], "authoring_version": 0, "name": "Corrected"},
    )
    assert corrected.status_code == 200, corrected.text


async def test_simple_patch_checks_child_field_denies_before_persistence(client, factory, tenant_a):
    company, user, auth, _, product = await create_simple(client, factory, tenant_a)
    await policy(factory, tenant_a, company, user, "catalog.item", "name", "write")
    response = await client.patch(
        f"/v1/companies/{company}/products/{product['id']}",
        headers=command_headers(auth),
        json={
            "revision": product["revision"],
            "authoring_version": 0,
            "brand_id": str(uuid7()),
            "name": "Denied item name",
        },
    )
    assert response.status_code == 403, response.text


async def test_expired_product_revision_identifies_reloadable_revision(
    client, factory, tenant_a, monkeypatch
):
    from catalog.tasks import simple_products

    company, _, auth, _, product = await create_simple(client, factory, tenant_a)
    native_codec = simple_products.revision_codec

    def expired_codec(*args, **kwargs):
        codec = native_codec(*args, **kwargs)
        clock = codec._clock
        monkeypatch.setattr(codec, "_clock", lambda: clock() + 86401)
        return codec

    monkeypatch.setattr(simple_products, "revision_codec", expired_codec)
    route = f"/v1/companies/{company}/products/{product['id']}"
    response = await client.patch(
        route,
        headers=command_headers(auth),
        json={"revision": product["revision"], "authoring_version": 0, "name": "Overnight edit"},
    )
    assert response.status_code == 422, response.text
    assert set(response.json()["error"]["fields"]) == {"revision"}
    assert "latest saved product" in response.json()["error"]["message"]
    monkeypatch.setattr(simple_products, "revision_codec", native_codec)
    latest = await client.get(route, headers=auth)
    assert latest.status_code == 200, latest.text
    assert latest.json()["name"] == product["name"]
    retried = await client.patch(
        route,
        headers=command_headers(auth),
        json={
            "revision": latest.json()["revision"],
            "authoring_version": 0,
            "name": "Overnight edit",
        },
    )
    assert retried.status_code == 200, retried.text
