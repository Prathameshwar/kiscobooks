"""The native pricing authoring contract consumed by the Console master pages."""

import json
from pathlib import Path

import pytest
from billing_platform.ids import uuid7

from tests.pricing_factories import setup_pricing
from tests.test_api import headers
from tests.test_unit_api import policy, seed_context

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_pricing_controls_and_capture(client, factory, tenant_a):
    root, current, _ = await setup_pricing(factory, tenant_a)
    captured = {}
    for entity in ("sales_channel", "price_level", "price_plan"):
        for operation in ("read", "create", "update"):
            response = await client.get(
                root + f"/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()
    levels = {field["key"]: field for field in captured["price_level:create"]["fields"]}
    assert levels["ordinal"]["control"]["minimum"] == 4
    assert levels["ordinal"]["control"]["maximum"] == 64
    plans = {field["key"]: field for field in captured["price_plan:create"]["fields"]}
    assert plans["currency"]["control"]["reference_source"] == "currencies"
    assert plans["price_level_id"]["control"]["reference_source"] == "price-levels"
    assert {choice["value"] for choice in plans["purpose"]["control"]["choices"]} == {
        "SALE",
        "PURCHASE",
        "REFERENCE_RETAIL",
    }
    for entity, editable in (("price_level", {"name", "is_active"}), ("price_plan", {"name"})):
        updated = captured[entity + ":update"]["fields"]
        assert {field["key"] for field in updated if field["writable"]} == editable
    assert not next(
        field for field in captured["sales_channel:update"]["fields"] if field["key"] == "is_active"
    )["writable"]
    destination = Path(__file__).resolve().parents[3] / ".tools/pricing-review/native-fields.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(captured, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    "entity,permission",
    [
        ("sales_channel", "sales_channel"),
        ("price_level", "price_plan"),
        ("price_plan", "price_plan"),
    ],
)
async def test_pricing_read_only_metadata(client, factory, tenant_a, entity, permission):
    root, _, ids = await setup_pricing(factory, tenant_a)
    current = headers(
        root.split("/")[-1],
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=[permission + ".read"],
    )
    response = await client.get(
        root + f"/entities/catalog.{entity}/field-set?operation=create", headers=current
    )
    assert response.status_code == 200, response.text
    assert not any(field["writable"] for field in response.json()["fields"])


@pytest.mark.parametrize("access", ["read", "write"])
async def test_pricing_metadata_respects_field_denies(client, factory, tenant_a, access):
    company, user = uuid7(), uuid7()
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        [policy(user, "name", access, entity="catalog.price_plan")],
    )
    current = headers(
        company, tenant=tenant_a, user=user, permission=["price_plan.read", "price_plan.manage"]
    )
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.price_plan/field-set?operation=update",
        headers=current,
    )
    assert response.status_code == 200, response.text
    field = next((field for field in response.json()["fields"] if field["key"] == "name"), None)
    assert field is None if access == "read" else field and not field["writable"]


async def test_pricing_metadata_scope_and_closed_query(client, factory, tenant_a):
    root, current, _ = await setup_pricing(factory, tenant_a)
    path = root + "/entities/catalog.price_plan/field-set"
    assert (await client.get(path)).status_code == 401
    for query in ("operation=publish", "operation=create&operation=update", "extra=true"):
        assert (await client.get(path + "?" + query, headers=current)).status_code == 422
    other, _, _ = await setup_pricing(factory, tenant_a)
    assert (
        await client.get(other + "/entities/catalog.price_plan/field-set", headers=current)
    ).status_code == 403
