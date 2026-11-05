"""Reusable API contract: bindings are undated; published revisions are dated."""

import pytest

from tests.unit_integrity_factories import setup_units

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_binding_list_undated_and_revision_list_dated(client, factory, tenant_a):
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}/unit-bindings"
    undated = await client.get(path + "?limit=50", headers=auth)
    assert undated.status_code == 200, undated.text
    rejected = await client.get(path + "?limit=50&as_of=2090-01-01", headers=auth)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["message"] == "this definition has no effective-date filter"
    binding = undated.json()["items"][0]
    revisions = await client.get(
        root + f"/item-unit-bindings/{binding['id']}/revisions?limit=200&as_of=2090-01-01",
        headers=auth,
    )
    assert revisions.status_code == 200, revisions.text
