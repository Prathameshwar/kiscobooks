import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.attributes import AttributeValue
from catalog.models import AttributeDefinition, AttributeOption, Item, ItemVariantKey
from tests.attribute_factories import seed_attributes
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_variant_option_restrictions_and_collision_fail_without_orphaning_values(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    item_path = root + f"/items/{ids['item']}"
    family_path = root + f"/product-families/{ids['product_family']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            digest, canonical = AttributeValue("TEXT", "Red").canonical()
            red = AttributeOption(
                tenant_id=tenant_a,
                company_id=company,
                definition_id=ids["attribute_definition"],
                code="RED",
                name="Red",
                value_type="TEXT",
                value_text="Red",
                value_hash=digest,
                canonical_value=canonical,
            )
            db.add(red)
            await db.flush()
            red_id = red.id
            item = await db.get(Item, ids["item"])
            assert item is not None
            unit_id = item.base_unit_id
    selected = {
        "definition_id": str(ids["attribute_definition"]),
        "value_type": "TEXT",
        "option_id": str(red_id),
    }
    denied = await client.put(
        item_path + "/attributes",
        headers=command_headers(auth),
        json={"expected_version": 1, "attributes": [selected]},
    )
    assert denied.status_code == 422 and "not permitted by the family" in denied.text, denied.text
    orphan = await client.put(
        family_path + "/attributes",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "attributes": [
                {
                    "definition_id": str(ids["attribute_definition"]),
                    "is_axis": True,
                    "is_required": True,
                    "position": 0,
                    "options": [str(red_id)],
                }
            ],
            "expected_default_item_version": 1,
            "default_item_attributes": [selected],
        },
    )
    assert orphan.status_code == 409 and "remain permitted" in orphan.text, orphan.text
    async with changed(
        factory,
        tenant_a,
        ItemVariantKey,
        ids["item_variant_key"],
        canonical_combination=b"corrupt-canonical",
    ):
        collision = await client.post(
            family_path + "/variants",
            headers=command_headers(auth),
            json={
                "expected_version": 1,
                "item": {"sku": "COLLISION", "name": "Collision", "base_unit_id": str(unit_id)},
                "attributes": [{**selected, "option_id": str(ids["attribute_option"])}],
            },
        )
        assert collision.status_code == 409 and "hash collision" in collision.text, collision.text
    values = await client.get(item_path + "/attributes", headers=auth)
    assert values.status_code == 200 and values.json()["items"][0]["option_id"] == str(
        ids["attribute_option"]
    ), values.text


async def test_optional_attributes_never_create_axes_or_accept_foreign_options(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    root = f"/v1/companies/{company}"
    family = root + f"/product-families/{product['family']['id']}/attributes"
    item = root + f"/items/{product['default_item']['id']}/attributes"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            definition = AttributeDefinition(
                tenant_id=tenant_a,
                company_id=company,
                code="OTHER",
                name="Other",
                value_type="TEXT",
                is_variant_capable=False,
            )
            db.add(definition)
            await db.flush()
            digest, canonical = AttributeValue("TEXT", "Other").canonical()
            option = AttributeOption(
                tenant_id=tenant_a,
                company_id=company,
                definition_id=definition.id,
                code="OTHER",
                name="Other",
                value_type="TEXT",
                value_text="Other",
                value_hash=digest,
                canonical_value=canonical,
            )
            db.add(option)
            await db.flush()
            other_option = option.id
    entry = {"definition_id": str(ids["attribute_definition"]), "position": 0}
    denied = await client.put(
        family,
        headers=command_headers(auth),
        json={"expected_version": 1, "attributes": [{**entry, "options": [str(other_option)]}]},
    )
    assert denied.status_code == 403 and "another attribute" in denied.text, denied.text
    declared = await client.put(
        family, headers=command_headers(auth), json={"expected_version": 1, "attributes": [entry]}
    )
    assert declared.status_code == 200, declared.text
    selected = await client.put(
        item,
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "attributes": [
                {
                    "definition_id": str(ids["attribute_definition"]),
                    "value_type": "TEXT",
                    "option_id": str(ids["attribute_option"]),
                }
            ],
        },
    )
    assert selected.status_code == 200, selected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemVariantKey.id))) == 0
