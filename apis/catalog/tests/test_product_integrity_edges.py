"""Cross-direction, future-date and dependency retirement regression cases."""

import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import FamilyGroupAssignment, Item
from tests.attribute_factories import seed_attributes
from tests.pricing_factories import create, foundation, guard, setup_pricing
from tests.test_commercial_api import command_headers
from tests.test_pricing_levels_units import feature
from tests.test_product_authoring import create_product
from tests.test_product_integrity_fixes import post_ok, put

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_new_alternate_validates_already_scheduled_base_revisions(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    item = (await client.get(path, headers=auth)).json()
    body: dict[str, Any] = {
        "expected_version": 1,
        "binding_id": str(ids["item_unit_binding"]),
        "code": "BASE",
        "role": "BASE",
        "unit_id": item["base_unit_id"],
        "numerator": 1,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "2",
        "valid_from": "2092-01-01",
    }
    revised = await post_ok(client, path + "/unit-revisions", auth, body)
    alternate = {key: value for key, value in body.items() if key != "binding_id"}
    alternate.update(
        expected_version=revised["item_version"],
        code="SALE",
        role="SALE",
        quantity_increment="1",
        valid_from="2091-01-01",
    )
    await post_ok(client, path + "/unit-bindings", auth, alternate, status=422)
    accepted = await post_ok(
        client, path + "/unit-bindings", auth, {**alternate, "quantity_increment": "2"}
    )
    assert accepted["item_version"] == revised["item_version"] + 1
    bindings = (await client.get(path + "/unit-bindings", headers=auth)).json()["items"]
    binding = next(row for row in bindings if row["code"] == "SALE")
    rows = (
        await client.get(root + f"/item-unit-bindings/{binding['id']}/revisions", headers=auth)
    ).json()["items"]
    for date in ("2091-01-01", "2092-01-01"):
        result = await client.post(
            path + "/quantity-preview",
            headers=auth,
            json={
                "as_of": date,
                "components": [{"unit_revision_id": rows[0]["id"], "quantity": "2"}],
            },
        )
        assert result.status_code == 200, result.text


async def test_tightening_options_rejects_existing_scalar_and_preserves_versions(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    root = f"/v1/companies/{company}"
    family = root + f"/product-families/{product['family']['id']}/attributes"
    item = root + f"/items/{product['default_item']['id']}/attributes"
    declaration = {"definition_id": str(ids["attribute_definition"]), "position": 0}
    await put(client, family, auth, {"expected_version": 1, "attributes": [declaration]})
    await put(
        client,
        item,
        auth,
        {
            "expected_version": 1,
            "attributes": [
                {
                    "definition_id": str(ids["attribute_definition"]),
                    "value_type": "TEXT",
                    "value_text": "Free text",
                }
            ],
        },
    )
    closed = {**declaration, "options": [str(ids["attribute_option"])]}
    await put(client, family, auth, {"expected_version": 2, "attributes": [closed]}, status=409)
    values = (await client.get(item, headers=auth)).json()["items"]
    detail = (await client.get(item + "/" + values[0]["id"], headers=auth)).json()
    assert detail["value_text"] == "Free text"
    cleared = await put(client, item, auth, {"expected_version": 2, "attributes": []})
    changed = await put(client, family, auth, {"expected_version": 2, "attributes": [closed]})
    assert changed["family_version"] == 3
    assert changed["item_version"] == cleared["item_version"]


async def test_future_descendant_active_assignment_blocks_ancestor_move(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    parent = await create(
        client,
        root,
        auth,
        "/item-groups",
        {
            "code": "PARENT",
            "name": "Parent",
            "valid_from": "2090-01-01",
        },
    )
    destination = await create(
        client,
        root,
        auth,
        "/item-groups",
        {
            "code": "TARGET",
            "name": "Target",
            "valid_from": "2090-01-01",
        },
    )
    child_path = root + f"/item-groups/{ids['item_group']}"
    await post_ok(
        client,
        child_path + "/reparent",
        auth,
        {
            "expected_version": 1,
            "expected_generation": destination["policy_generation"],
            "parent_group_id": parent["id"],
            "effective_from": "2092-01-01",
        },
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assignment = await db.get(FamilyGroupAssignment, ids["family_group_assignment"])
            assert item is not None and assignment is not None
            item.status = "ACTIVE"
            assignment.valid_from = dt.date(2092, 1, 1)
    parent_path = root + f"/item-groups/{parent['id']}"
    before = (await client.get(parent_path, headers=auth)).json()
    await post_ok(
        client,
        parent_path + "/reparent",
        auth,
        {
            "expected_version": before["row_version"],
            "expected_generation": before["policy_generation"],
            "parent_group_id": destination["id"],
            "effective_from": "2091-01-01",
        },
        status=409,
    )
    assert (await client.get(parent_path, headers=auth)).json() == before
    # A no-op and an unrelated branch remain usable.
    await post_ok(
        client,
        parent_path + "/reparent",
        auth,
        {
            "expected_version": before["row_version"],
            "expected_generation": before["policy_generation"],
            "parent_group_id": None,
            "effective_from": "2091-01-01",
        },
    )
    target_path = root + f"/item-groups/{destination['id']}"
    current = (await client.get(target_path, headers=auth)).json()
    await post_ok(
        client,
        target_path + "/reparent",
        auth,
        {
            "expected_version": current["row_version"],
            "expected_generation": current["policy_generation"],
            "parent_group_id": parent["id"],
            "effective_from": "2091-01-01",
        },
    )


async def test_policy_only_price_level_dependency_and_unused_retirement(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    await feature(factory, tenant_a, uuid.UUID(root.rsplit("/", 1)[1]), ids["actor_user"])
    setup = await foundation(client, root, auth, ids)
    levels = (await client.get(root + "/price-levels", headers=auth)).json()["items"]
    second = next(row for row in levels if row["code"] == "PRICE2")
    third = next(row for row in levels if row["code"] == "PRICE3")
    await create(
        client,
        root,
        auth,
        "/company-pricing-policies",
        {
            **guard(setup["series"]),
            "default_level_id": setup["level"]["id"],
            "missing_price_policy": "FALLBACK",
            "fallback_level_id": second["id"],
            "valid_from": "2091-01-01",
            "supersedes_id": setup["policy"]["id"],
            "expected_previous_version": 1,
        },
    )
    for level, status in ((second, 409), (third, 200)):
        response = await client.patch(
            root + "/price-levels/" + level["id"],
            headers=command_headers(auth),
            json={"expected_version": 1, "name": "Level", "is_active": False},
        )
        assert response.status_code == status, response.text
    renamed = await client.patch(
        root + "/price-levels/" + second["id"],
        headers=command_headers(auth),
        json={"expected_version": 1, "name": "Renamed", "is_active": True},
    )
    assert renamed.status_code == 200, renamed.text
