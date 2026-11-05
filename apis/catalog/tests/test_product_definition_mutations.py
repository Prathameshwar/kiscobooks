import uuid

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_classification_replacement_overlap_and_native_attribute_invariants(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    path = base + f"/product-families/{ids['product_family']}"
    maker = {
        "expected_version": 1,
        "manufacturer_id": str(ids["manufacturer"]),
        "valid_from": "2090-01-01",
    }
    duplicate = await client.post(
        path + "/manufacturers", headers=command_headers(auth), json=maker
    )
    assert duplicate.status_code == 409, duplicate.text
    added = await client.post(
        path + "/manufacturers",
        headers=command_headers(auth),
        json={**maker, "role": "ASSEMBLER", "valid_from": "2091-01-01", "valid_to": "2092-01-01"},
    )
    assert added.status_code == 200, added.text
    group_body = {
        "expected_version": 2,
        "group_id": str(ids["item_group"]),
        "valid_from": "2091-01-01",
    }
    assigned = await client.post(path + "/groups", headers=command_headers(auth), json=group_body)
    assert assigned.status_code == 200, assigned.text
    bad_history = await client.post(
        path + "/groups",
        headers=command_headers(auth),
        json={**group_body, "expected_version": 3, "valid_from": "2089-01-01"},
    )
    assert bad_history.status_code == 409, bad_history.text
    service_group = await client.post(
        base + "/item-groups",
        headers=command_headers(auth),
        json={
            "code": "SERVICES",
            "name": "Services",
            "allowed_kind": "SERVICE",
            "valid_from": "2090-01-01",
        },
    )
    assert service_group.status_code == 201, service_group.text
    bad_kind = await client.post(
        path + "/groups",
        headers=command_headers(auth),
        json={
            **group_body,
            "expected_version": 3,
            "group_id": service_group.json()["id"],
            "valid_from": "2092-01-01",
        },
    )
    assert bad_kind.status_code == 422, bad_kind.text
    category = {
        "scheme_id": str(ids["category_scheme"]),
        "category_id": str(ids["item_category"]),
        "is_primary": True,
    }
    duplicates = await client.put(
        path + "/categories",
        headers=command_headers(auth),
        json={"expected_version": 3, "categories": [category, category]},
    )
    assert duplicates.status_code == 422, duplicates.text
    second = await client.post(
        base + "/item-categories",
        headers=command_headers(auth),
        json={"code": "SECOND", "name": "Second", "scheme_id": str(ids["category_scheme"])},
    )
    assert second.status_code == 201, second.text
    second_category = {**category, "category_id": second.json()["id"]}
    overfull = await client.put(
        path + "/categories",
        headers=command_headers(auth),
        json={"expected_version": 3, "categories": [category, second_category]},
    )
    assert overfull.status_code == 422, overfull.text
    replaced = await client.put(
        path + "/categories",
        headers=command_headers(auth),
        json={"expected_version": 3, "categories": [second_category]},
    )
    assert replaced.status_code == 200, replaced.text
    declaration = {
        "definition_id": str(ids["attribute_definition"]),
        "is_axis": True,
        "is_required": True,
        "position": 0,
        "options": [str(ids["attribute_option"])],
    }
    selected = {
        "definition_id": str(ids["attribute_definition"]),
        "option_id": str(ids["attribute_option"]),
        "value_type": "TEXT",
    }
    for entries, status in (
        ([declaration, declaration], 422),
        ([], 409),
        ([{**declaration, "options": []}], 409),
        ([{**declaration, "is_required": False}], 422),
    ):
        invalid = await client.put(
            path + "/attributes",
            headers=command_headers(auth),
            json={
                "expected_version": 4,
                "attributes": entries,
                "expected_default_item_version": 1,
                "default_item_attributes": [selected],
            },
        )
        assert invalid.status_code == status, invalid.text
    valid = await client.put(
        path + "/attributes",
        headers=command_headers(auth),
        json={
            "expected_version": 4,
            "attributes": [declaration],
            "expected_default_item_version": 1,
            "default_item_attributes": [selected],
        },
    )
    assert valid.status_code == 200, valid.text
    item_path = base + f"/items/{ids['item']}/attributes"
    for value_entries, status in (
        ([selected, selected], 422),
        ([{**selected, "value_type": "INTEGER"}], 422),
        ([{**selected, "value_text": "mixed"}], 422),
        ([{**selected, "option_id": None, "value_text": "scalar axis"}], 422),
    ):
        invalid = await client.put(
            item_path,
            headers=command_headers(auth),
            json={"expected_version": 2, "attributes": value_entries},
        )
        assert invalid.status_code == status, invalid.text
    reassigned = await client.put(
        item_path,
        headers=command_headers(auth),
        json={"expected_version": 2, "attributes": [selected]},
    )
    assert reassigned.status_code == 200, reassigned.text
    # The dated group change requires an explicit new configuration adoption.
    stale = await client.get(
        base + f"/items/{ids['item']}/configuration", headers=auth, params={"as_of": "2091-01-01"}
    )
    assert stale.status_code == 409, stale.text
