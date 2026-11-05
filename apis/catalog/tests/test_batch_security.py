"""New batch choices and commands retain tenant and permission boundaries."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models.product_stock_choice import ItemStockChoice
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers


async def test_stock_choices_are_tenant_isolated_and_immutable(factory, tenant_a, tenant_b):
    for tenant in (tenant_a, tenant_b):
        company, ids = await seed_definitions(factory, tenant)
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(
                    ItemStockChoice(
                        tenant_id=tenant,
                        company_id=company,
                        item_id=ids["item"],
                        batch_enabled=True,
                        row_version=1,
                    )
                )
    with tenant_scope(tenant_a):
        async with factory() as db:
            choices = list(await db.scalars(select(ItemStockChoice)))
            assert len(choices) == 1 and choices[0].tenant_id == tenant_a
            choices[0].batch_enabled = False
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()


async def test_batch_price_command_denies_unauthorized_requests(client, factory, tenant_a):
    company, ids = await seed_definitions(factory, tenant_a)
    root = f"/v1/companies/{company}/batch-prices"
    body = {
        "item_id": str(ids["item"]),
        "lot_id": str(uuid7()),
        "unit_revision_id": str(ids["item_unit_revision"]),
        "valid_from": "2090-01-01",
        "expected_generation": 1,
        "expected_source_version": 1,
        "prices": [],
    }
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=["catalog.readiness.read"]
    )
    for supplied, status in (({}, 401), (auth, 403)):
        response = await client.post(
            root, headers=supplied | {"Idempotency-Key": str(uuid7())}, json=body
        )
        assert response.status_code == status, response.text
    response = await client.post(
        f"/v1/companies/{uuid.uuid4()}/batch-prices",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert response.status_code == 403, response.text
