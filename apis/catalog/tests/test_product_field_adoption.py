"""Real product writes remain usable while candidate contracts await review."""

import uuid
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_product_custom_fields import install

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def manager(company: uuid.UUID, tenant: uuid.UUID, user: uuid.UUID) -> dict[str, str]:
    return headers(
        company,
        tenant=tenant,
        user=user,
        permission=["custom_field.manage", "item.read", "item.update"],
    )


async def review_and_adopt(
    client: httpx.AsyncClient, root: str, auth: dict[str, str]
) -> dict[str, Any]:
    result = await client.post(root + "/preview", headers=auth)
    assert result.status_code == 200, result.text
    assert result.json()["eligible"], result.text
    adopted = await client.post(
        root, headers=command_headers(auth), json={"preview_token": result.json()["preview_token"]}
    )
    assert adopted.status_code == 200, adopted.text
    return cast(dict[str, Any], adopted.json())


async def test_candidate_requiredness_does_not_break_existing_product_edits(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    definition: dict[str, Any] = {"requires_adoption": True, "is_searchable": False}
    await install(factory, tenant_a, company, user, [definition])
    base = f"/v1/companies/{company}"
    root = base + "/entities/catalog.item/custom-field-adoption"
    admin = manager(company, tenant_a, user)
    await review_and_adopt(client, root, admin)
    created = await client.post(
        base + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    item = created.json()["default_item"]
    definition["validation"] = {"required": True}
    await install(factory, tenant_a, company, user, [definition], version=4)
    route = base + "/items/" + item["id"]
    edited = await client.patch(
        route, headers=command_headers(auth), json={"expected_version": 1, "name": "Still editable"}
    )
    assert edited.status_code == 200, edited.text
    rejected = await client.post(root + "/preview", headers=admin)
    assert rejected.status_code == 200, rejected.text
    assert not rejected.json()["eligible"]
    blocked = await client.post(
        root,
        headers=command_headers(admin),
        json={"preview_token": rejected.json()["preview_token"]},
    )
    assert blocked.status_code == 409, blocked.text
    backfilled = await client.patch(
        route,
        headers=command_headers(auth),
        json={"expected_version": 2, "custom_fields": {"cf_note": "filled"}},
    )
    assert backfilled.status_code == 200, backfilled.text
    await review_and_adopt(client, root, admin)
    invalid = await client.patch(
        route,
        headers=command_headers(auth),
        json={"expected_version": 3, "custom_fields": {"cf_note": None}},
    )
    assert invalid.status_code == 422, invalid.text


async def test_product_change_invalidates_review_and_adoption_replay_rechecks_access(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(factory, tenant_a, company, user, [{"requires_adoption": True}])
    base = f"/v1/companies/{company}"
    root = base + "/entities/catalog.item/custom-field-adoption"
    admin = manager(company, tenant_a, user)
    preview = await client.post(root + "/preview", headers=admin)
    assert preview.status_code == 200, preview.text
    created = await client.post(
        base + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    result = await client.post(
        root,
        headers=command_headers(admin),
        json={"preview_token": preview.json()["preview_token"]},
    )
    assert result.status_code == 409, result.text
    preview = await client.post(root + "/preview", headers=admin)
    command = {"preview_token": preview.json()["preview_token"]}
    request_headers = command_headers(admin)
    accepted = await client.post(root, headers=request_headers, json=command)
    assert accepted.status_code == 200, accepted.text
    replay = await client.post(root, headers=request_headers, json=command)
    assert replay.status_code == 200, replay.text
    assert replay.json() == accepted.json()
    denied = headers(company, tenant=tenant_a, user=user, permission=["item.read"])
    denied["Idempotency-Key"] = request_headers["Idempotency-Key"]
    replay = await client.post(root, headers=denied, json=command)
    assert replay.status_code == 403, replay.text


async def test_company_unique_adoption_prepares_claims_and_search_together(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "requires_adoption": True,
                "is_searchable": True,
                "validation": {"unique_within": "company"},
            }
        ],
    )
    base = f"/v1/companies/{company}"
    root = base + "/entities/catalog.item/custom-field-adoption"
    await review_and_adopt(client, root, manager(company, tenant_a, user))
    body["default_item"]["custom_fields"] = {"cf_note": "same"}
    first = await client.post(base + "/product-families", headers=command_headers(auth), json=body)
    assert first.status_code == 201, first.text
    body["code"] = "SECOND"
    body["default_item"]["sku"] = "SECOND"
    second = await client.post(base + "/product-families", headers=command_headers(auth), json=body)
    assert second.status_code == 409, second.text


async def test_adoption_rows_are_tenant_isolated_and_rollback_is_atomic(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from billing_platform.db import tenant_scope
    from billing_platform.ids import uuid7
    from sqlalchemy import select

    from catalog.models.field_adoption import CustomFieldAdoption

    own_ids = {}
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            async with factory.begin() as db:
                created = CustomFieldAdoption(
                    tenant_id=tenant, company_id=uuid7(), entity_type="catalog.item", definitions=[]
                )
                db.add(created)
                await db.flush()
                own_ids[tenant] = created.id
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            async with factory() as db:
                assert list(await db.scalars(select(CustomFieldAdoption.id))) == [own_ids[tenant]]
                row = await db.get(CustomFieldAdoption, own_ids[tenant])
                assert row is not None
                row.definitions = [{"key": "cf_not_committed"}]
                await db.flush()
                await db.rollback()
            async with factory() as db:
                row = await db.get(CustomFieldAdoption, own_ids[tenant])
                assert row is not None and row.definitions == []
