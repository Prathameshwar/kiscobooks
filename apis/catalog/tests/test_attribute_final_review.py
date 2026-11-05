"""Confirm the UI can rename a native option without reading its protected value."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import AttributeOption
from tests.test_attribute_practical_review import setup_axis
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_option_label_edit_preserves_read_protected_value(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids, auth, _ = await setup_axis(client, factory, tenant_a)
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.attribute_option",
        "value_text",
        "read",
    )
    route = f"/v1/companies/{company}/attribute-options/{ids['attribute_option']}"
    detail = await client.get(route, headers=auth)
    assert detail.status_code == 200, detail.text
    assert "value_text" not in detail.json()
    key = command_headers(auth)
    body = {"expected_version": 1, "name": "Blue label"}
    updated = await client.patch(route, headers=key, json=body)
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Blue label" and "value_text" not in updated.json()
    replay = await client.patch(route, headers=key, json=body)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(tenant_a):
        async with factory() as db:
            stored = await db.get(AttributeOption, ids["attribute_option"])
            assert stored and stored.value_text == "Blue"
