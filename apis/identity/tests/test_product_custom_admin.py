"""Product custom-field regression coverage."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies

PERMISSIONS = [
    "custom_field.manage",
    "field_config.manage",
    "field_policy.manage",
    "company.read",
    "company.update",
]


@pytest.mark.parametrize("entity", ["catalog.item", "catalog.product_family"])
async def test_admin_can_add_product_definition(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    entity: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    auth = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMISSIONS)])
    response = await client.post(
        "/v1/custom-field-definitions",
        headers=auth,
        json={
            "entity_type": entity,
            "company_id": str(company),
            "label": "Warranty note",
            "definition": {"key": "cf_warranty_note", "data_type": "text"},
        },
    )
    assert response.status_code == 201, response.text


async def test_admin_can_configure_product_field_layout(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    auth = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMISSIONS)])
    response = await client.put(
        "/v1/entities/catalog.item/field-config/name",
        headers=auth,
        json={"label_override": "Product name"},
    )
    assert response.status_code == 200, response.text


async def test_admin_can_define_product_field_policy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    reader = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=reader))
        await session.commit()
    auth = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant([*PERMISSIONS, "item.update"])]
    )
    response = await client.post(
        "/v1/field-policies",
        headers=auth,
        json={
            "entity_type": "catalog.item",
            "subject_type": "user",
            "subject_id": str(reader),
            "field_key": "name",
            "access": "write",
            "effect": "deny",
            "reason": "Restrict editing",
        },
    )
    assert response.status_code == 201, response.text


async def test_company_admin_manages_scoped_definition_layout_and_protected_revision(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    auth = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant([*PERMISSIONS, "item.update"], scope_type="company", scope_id=company)],
    )
    body = {
        "entity_type": "catalog.item",
        "company_id": str(company),
        "label": "Note",
        "definition": {"key": "cf_note", "data_type": "text"},
    }
    created = await client.post("/v1/custom-field-definitions", headers=auth, json=body)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["requires_adoption"] is True
    listing = await client.get(
        "/v1/custom-field-definitions",
        headers=auth,
        params={"entity_type": "catalog.item", "company_id": str(company)},
    )
    assert listing.status_code == 200, listing.text
    assert [item["id"] for item in listing.json()["items"]] == [row["id"]]
    route = "/v1/entities/catalog.item/field-config/custom_field:cf_note"
    layout = await client.put(
        route,
        headers=auth,
        params={"company_id": str(company)},
        json={"label_override": "Scoped label"},
    )
    assert layout.status_code == 200, layout.text
    assert layout.json()["field_key"] == "cf_note"
    body["label"] = "New label"
    stale = await client.put("/v1/custom-field-definitions/" + row["id"], headers=auth, json=body)
    assert stale.status_code == 409, stale.text
    current = await client.put(
        "/v1/custom-field-definitions/" + row["id"],
        headers=auth,
        json={**body, "expected_digest": row["digest"]},
    )
    assert current.status_code == 200, current.text
    stale = await client.put(
        "/v1/custom-field-definitions/" + row["id"],
        headers=auth,
        json={**body, "expected_digest": row["digest"]},
    )
    assert stale.status_code == 409, stale.text
    contracts = await client.get(
        "/v1/entities/catalog.item/custom-field-contract",
        headers=auth,
        params={"company_id": str(company)},
    )
    policies = await client.get(
        "/v1/field-policies",
        headers=auth,
        params={"entity_type": "catalog.item", "company_id": str(company)},
    )
    assert policies.status_code == 200, policies.text
    denied = await client.get(
        "/v1/field-policies", headers=auth, params={"entity_type": "catalog.item"}
    )
    assert denied.status_code == 403
    assert contracts.status_code == 200, contracts.text
    assert "catalog.brands" in contracts.json()["option_sources"]


async def test_product_dynamic_source_parent_is_validated_before_publication(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    auth = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMISSIONS)])
    response = await client.post(
        "/v1/custom-field-definitions",
        headers=auth,
        json={
            "entity_type": "catalog.item",
            "company_id": str(company),
            "label": "Category",
            "definition": {
                "key": "cf_category",
                "data_type": "dynamic_select",
                "option_source_key": "catalog.item_categories",
            },
        },
    )
    assert response.status_code == 422, response.text


async def test_static_default_must_be_an_active_choice(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    auth = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMISSIONS)])
    response = await client.post(
        "/v1/custom-field-definitions",
        headers=auth,
        json={
            "entity_type": "catalog.item",
            "company_id": str(company),
            "label": "Colour",
            "definition": {
                "key": "cf_colour",
                "data_type": "select",
                "choices": [{"value": "red", "label": "Red"}],
                "default_value": "missing",
            },
        },
    )
    assert response.status_code == 422, response.text
