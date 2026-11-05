"""Reviewed medicine evidence cannot be asserted through item custom fields."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.api.voucher_sources import facts as voucher_facts
from catalog.models.classification import CatalogPolicyState
from catalog.models.regulatory import ItemRegulatoryClassification
from tests.configuration_factories import setup_configuration
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_regulatory_history_is_reviewed_dated_scoped_and_idempotent(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user, auth, body = await setup_configuration(factory, tenant_a)
    created = await client.post(
        f"/v1/companies/{company}/product-families",
        headers=command_headers(auth),
        json=body,
    )
    assert created.status_code == 201, created.text
    item = created.json()["default_item"]["id"]
    root = f"/v1/companies/{company}/items/{item}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            generation = await db.scalar(
                select(CatalogPolicyState.generation).where(
                    CatalogPolicyState.company_id == company
                )
            )
    assert generation is not None
    proposal = {
        "expected_generation": generation,
        "expected_source_version": 2,
        "valid_from": "2090-01-01",
        "product_kind": "MEDICINE",
        "licence_class": "C_C1_EXCLUDING_X",
        "prescription_schedule": "H1",
        "source_reference": "Reviewed drug label and official schedule",
        "source_url": "https://example.invalid/reviewed-source",
        "source_sha256": "a" * 64,
        "review_reason": "Approved for this SKU",
    }
    write_auth = headers(
        company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS)
    )
    command_auth = command_headers(write_auth)
    route = root + "/regulatory-classifications"
    assert (await client.post(route, headers=command_headers({}), json=proposal)).status_code == 401
    no_review = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=sorted(CATALOG_PERMISSIONS - {"item.activate"}),
    )
    assert (
        await client.post(route, headers=command_headers(no_review), json=proposal)
    ).status_code == 403
    assert (
        await client.post(
            route,
            headers=command_headers(write_auth),
            json={**proposal, "prescription_schedule": "X"},
        )
    ).status_code == 422
    response = await client.post(route, headers=command_auth, json=proposal)
    assert response.status_code == 201, response.text
    replay = await client.post(route, headers=command_auth, json=proposal)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    effective = await client.get(
        root + "/regulatory-classification?as_of=2090-01-01", headers=write_auth
    )
    assert effective.status_code == 200, effective.text
    assert effective.json()["id"] == response.json()["id"]
    assert effective.json()["prescription_schedule"] == "H1"
    assert effective.json()["reviewed_by"] == str(user)
    item_facts = await client.get(root + "/effective-facts?as_of=2090-01-01", headers=write_auth)
    assert item_facts.status_code == 200, item_facts.text
    assert item_facts.json()["regulatory"]["id"] == response.json()["id"]
    assert item_facts.json()["stock_execution"]["state"] == "UNAVAILABLE"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            snapshot, cursor = await voucher_facts(
                db, tenant_a, company, "item_regulatory_classification", None, 1
            )
    assert cursor is None
    assert snapshot["masters"][0]["source_id"] == response.json()["id"]
    assert snapshot["masters"][0]["facts"]["item_id"] == item
    assert snapshot["masters"][0]["facts"]["source_sha256"] == "a" * 64
    prior = await client.get(
        root + "/regulatory-classification?as_of=2089-12-31", headers=write_auth
    )
    assert prior.status_code == 200 and prior.json() is None
    wrong = await client.get(
        f"/v1/companies/{uuid.uuid4()}/items/{item}/regulatory-classification?as_of=2090-01-01",
        headers=write_auth,
    )
    assert wrong.status_code == 403
    overlap = await client.post(
        route,
        headers=command_headers(write_auth),
        json={
            **proposal,
            "expected_generation": response.json()["policy_generation"],
            "valid_from": "2091-01-01",
        },
    )
    assert overlap.status_code == 409
    replacement = await client.post(
        route,
        headers=command_headers(write_auth),
        json={
            **proposal,
            "expected_generation": response.json()["policy_generation"],
            "valid_from": "2091-01-01",
            "supersedes_id": response.json()["id"],
            "expected_previous_version": 1,
            "prescription_schedule": "H",
            "source_sha256": "b" * 64,
            "review_reason": "Reviewed new official classification",
        },
    )
    assert replacement.status_code == 201, replacement.text
    earlier = await client.get(
        root + "/regulatory-classification?as_of=2090-12-31", headers=write_auth
    )
    later = await client.get(
        root + "/regulatory-classification?as_of=2091-01-01", headers=write_auth
    )
    assert earlier.status_code == 200 and earlier.json()["prescription_schedule"] == "H1"
    assert earlier.json()["valid_to"] == "2090-12-31"
    assert later.status_code == 200 and later.json()["prescription_schedule"] == "H"
    with tenant_scope(tenant_b):
        async with factory.begin() as db:
            assert list(await db.scalars(select(ItemRegulatoryClassification))) == []


async def test_food_classification_requires_category_and_reaches_signed_source(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, body = await setup_configuration(factory, tenant_a)
    created = await client.post(
        f"/v1/companies/{company}/product-families",
        headers=command_headers(auth),
        json=body,
    )
    assert created.status_code == 201, created.text
    item = created.json()["default_item"]["id"]
    root = f"/v1/companies/{company}/items/{item}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            generation = await db.scalar(
                select(CatalogPolicyState.generation).where(
                    CatalogPolicyState.company_id == company
                )
            )
    assert generation is not None
    proposal = {
        "expected_generation": generation,
        "expected_source_version": 2,
        "valid_from": "2090-01-01",
        "product_kind": "FOOD",
        "food_category_code": "DAIRY.MILK",
        "source_reference": "Reviewed food category evidence",
        "source_url": "https://example.invalid/food-review",
        "source_sha256": "c" * 64,
        "review_reason": "Verified for this packaged SKU",
    }
    write_auth = headers(
        company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS)
    )
    route = root + "/regulatory-classifications"
    missing = {key: value for key, value in proposal.items() if key != "food_category_code"}
    assert (
        await client.post(route, headers=command_headers(write_auth), json=missing)
    ).status_code == 422
    medicine_axis = proposal | {"licence_class": "C_C1_EXCLUDING_X"}
    assert (
        await client.post(route, headers=command_headers(write_auth), json=medicine_axis)
    ).status_code == 422
    response = await client.post(route, headers=command_headers(write_auth), json=proposal)
    assert response.status_code == 201, response.text
    resolved = await client.get(
        root + "/regulatory-classification?as_of=2090-01-01", headers=write_auth
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["food_category_code"] == "DAIRY.MILK"
    assert resolved.json()["licence_class"] is None
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            snapshot, _ = await voucher_facts(
                db, tenant_a, company, "item_regulatory_classification", None, 1
            )
    assert snapshot["masters"][0]["facts"]["food_category_code"] == "DAIRY.MILK"
