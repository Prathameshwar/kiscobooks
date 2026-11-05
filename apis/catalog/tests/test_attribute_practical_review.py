"""Practical attribute regressions: measurements, catalog growth and safe replacement."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    FamilyAttributeOption,
    Item,
    ItemAttributeValue,
    ItemVariantKey,
    ProductFamily,
)
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_measured_integer_value_can_be_saved(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    root = f"/v1/companies/{company}"
    result = await client.post(
        root + "/attribute-definitions",
        headers=command_headers(auth),
        json={
            "code": "COUNT",
            "name": "Piece count",
            "value_type": "INTEGER",
            "measurement_dimension": "COUNT",
        },
    )
    assert result.status_code == 201, result.text
    definition = result.json()["id"]
    result = await client.put(
        root + f"/product-families/{product['family']['id']}/attributes",
        headers=command_headers(auth),
        json={"expected_version": 1, "attributes": [{"definition_id": definition, "position": 0}]},
    )
    assert result.status_code == 200, result.text
    result = await client.put(
        root + f"/items/{product['default_item']['id']}/attributes",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "attributes": [
                {
                    "definition_id": definition,
                    "value_type": "INTEGER",
                    "value_integer": "2",
                    "unit_id": product["default_item"]["base_unit_id"],
                }
            ],
        },
    )
    assert result.status_code == 200, result.text

    form = await client.get(
        root + f"/items/{product['default_item']['id']}/attribute-form", headers=auth
    )
    assert form.status_code == 200, form.text
    assert form.json()["fields"][0]["value"]["value_integer"] == "2"
    assert form.json()["fields"][0]["unit_label"]


async def test_explicit_empty_default_values_clear_optional_attributes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    root = f"/v1/companies/{company}"
    created = await client.post(
        root + "/attribute-definitions",
        headers=command_headers(auth),
        json={"code": "NOTE", "name": "Material note", "value_type": "TEXT"},
    )
    assert created.status_code == 201, created.text
    definition = created.json()["id"]
    body = {
        "expected_version": 1,
        "expected_default_item_version": 1,
        "attributes": [{"definition_id": definition, "position": 0}],
        "default_item_attributes": [
            {"definition_id": definition, "value_type": "TEXT", "value_text": "old"}
        ],
    }
    route = root + f"/product-families/{product['family']['id']}/attributes"
    first = await client.put(route, headers=command_headers(auth), json=body)
    assert first.status_code == 200, first.text
    cleared = await client.put(
        route,
        headers=command_headers(auth),
        json={
            **body,
            "expected_version": 2,
            "expected_default_item_version": 2,
            "default_item_attributes": [],
        },
    )
    assert cleared.status_code == 200, cleared.text
    values = await client.get(
        root + f"/items/{product['default_item']['id']}/attributes", headers=auth
    )
    assert values.json()["items"] == []
    assert cleared.json()["item_version"] == 3


async def setup_axis(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, dict[str, uuid.UUID], dict[str, str], str]:
    company, ids = await seed_definitions(factory, tenant)
    auth = headers(
        company, tenant=tenant, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    created = await client.post(
        f"/v1/companies/{company}/attribute-options",
        headers=command_headers(auth),
        json={
            "definition_id": str(ids["attribute_definition"]),
            "code": "RED",
            "name": "Red",
            "value_type": "TEXT",
            "value_text": "Red",
        },
    )
    assert created.status_code == 201, created.text
    return company, ids, auth, created.json()["id"]


@pytest.mark.parametrize("active", [False, True])
async def test_allowed_options_can_expand_without_rewriting_existing_sku_identity(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    active: bool,
) -> None:
    company, ids, auth, red = await setup_axis(client, factory, tenant_a)
    if active:
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                family = await db.get(ProductFamily, ids["product_family"])
                item = await db.get(Item, ids["item"])
                assert family and item
                family.status = item.status = "ACTIVE"
    response = await client.put(
        f"/v1/companies/{company}/product-families/{ids['product_family']}/attributes",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "attributes": [
                {
                    "definition_id": str(ids["attribute_definition"]),
                    "position": 0,
                    "is_axis": True,
                    "is_required": True,
                    "options": [str(ids["attribute_option"]), red],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.get(ItemVariantKey, ids["item_variant_key"]) is not None
            assert await db.get(ItemAttributeValue, ids["item_attribute_value"]) is not None
            item = await db.get(Item, ids["item"])
            assert item and item.row_version == 1


async def test_active_family_accepts_a_new_draft_variant_and_its_authoring(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, red = await setup_axis(client, factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            item = await db.get(Item, ids["item"])
            assert family and item
            family.status = item.status = "ACTIVE"
            unit = str(item.base_unit_id)
            db.add(
                FamilyAttributeOption(
                    tenant_id=tenant_a,
                    company_id=company,
                    family_id=family.id,
                    definition_id=ids["attribute_definition"],
                    option_id=uuid.UUID(red),
                )
            )
    root = f"/v1/companies/{company}"
    values = [
        {"definition_id": str(ids["attribute_definition"]), "value_type": "TEXT", "option_id": red}
    ]
    created = await client.post(
        root + f"/product-families/{ids['product_family']}/variants",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "item": {"sku": "RED", "name": "Red SKU", "base_unit_id": unit},
            "attributes": values,
        },
    )
    assert created.status_code == 200, created.text
    result = await client.put(
        root + f"/items/{created.json()['item_id']}/attributes",
        headers=command_headers(auth),
        json={"expected_version": 1, "attributes": values},
    )
    assert result.status_code == 200, result.text
    rejected = await client.put(
        root + f"/items/{ids['item']}/attributes",
        headers=command_headers(auth),
        json={"expected_version": 1, "attributes": values},
    )
    assert rejected.status_code == 409, rejected.text


async def test_unchanged_sku_selections_keep_their_row_identity(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    response = await client.put(
        f"/v1/companies/{company}/items/{ids['item']}/attributes",
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
    assert response.status_code == 200, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.get(ItemAttributeValue, ids["item_attribute_value"]) is not None
            assert await db.get(ItemVariantKey, ids["item_variant_key"]) is not None


async def test_readiness_revalidates_stored_option_type(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(ItemAttributeValue, ids["item_attribute_value"])
            assert row
            row.value_type = "BOOLEAN"
    response = await client.get(
        f"/v1/companies/{company}/items/{ids['item']}/requirements",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert response.status_code == 200, response.text
    assert "attribute:" + str(ids["attribute_definition"]) in response.json()["missing"]


async def test_active_family_option_changes_replay_and_reject_structure_changes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, red = await setup_axis(client, factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family
            family.status = "ACTIVE"
    route = f"/v1/companies/{company}/product-families/{ids['product_family']}/attributes"
    entry = {
        "definition_id": str(ids["attribute_definition"]),
        "position": 0,
        "is_axis": True,
        "is_required": True,
        "options": [str(ids["attribute_option"]), red],
    }
    for invalid in [
        {**entry, "position": 2},
        {**entry, "is_required": False},
        {**entry, "options": [red]},
    ]:
        result = await client.put(
            route,
            headers=command_headers(auth),
            json={"expected_version": 1, "attributes": [invalid]},
        )
        assert result.status_code == 409, result.text
    key = command_headers(auth)
    body = {"expected_version": 1, "attributes": [entry]}
    first = await client.put(route, headers=key, json=body)
    assert first.status_code == 200, first.text
    replay = await client.put(route, headers=key, json=body)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["family_version"] == 2
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.get(FamilyAttributeOption, ids["family_attribute_option"]) is not None


async def test_default_clear_has_distinct_retry_identity_without_changing_legacy_omission(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import Any

    from billing_platform.idempotency import execute_idempotent as original

    from catalog.schemas.product_authoring import FamilyAttributesInput
    from catalog.tasks import product_commands

    company, _, auth, product = await create_product(client, factory, tenant_a)
    requests = []

    async def capture(*args: Any, **kwargs: Any) -> Any:
        requests.append(args[1].request)
        return await original(*args, **kwargs)

    monkeypatch.setattr(product_commands, "execute_idempotent", capture)
    route = f"/v1/companies/{company}/product-families/{product['family']['id']}/attributes"
    body = {"expected_version": 1, "expected_default_item_version": 1, "attributes": []}
    key = command_headers(auth)
    first = await client.put(route, headers=key, json=body)
    assert first.status_code == 200, first.text
    legacy = {
        "id": product["family"]["id"],
        "body": FamilyAttributesInput.model_validate(body).model_dump(mode="json"),
    }
    assert requests[0] == legacy
    clear = await client.put(route, headers=key, json={**body, "default_item_attributes": []})
    assert clear.status_code == 422, clear.text
    assert clear.json()["error"]["code"] == "idempotency_key_reused"
    replay = await client.put(route, headers=key, json=body)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
