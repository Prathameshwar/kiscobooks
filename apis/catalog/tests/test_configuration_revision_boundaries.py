import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CatalogPolicyState,
    ProductConfigurationDraft,
    ProductConfigurationScope,
    ProductNumericDefault,
)
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_configuration_replacement_dates_and_version_bounds(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    scopes = base + "/product-configuration-scopes"
    drafts = base + "/product-configurations"
    scope_id = ids["product_configuration_scope"]
    duplicate = await client.post(
        scopes, headers=command_headers(auth), json={"scope_kind": "COMPANY"}
    )
    assert duplicate.status_code == 409, duplicate.text
    published = await client.get(
        drafts + f"/{ids['product_configuration_draft']}/preview", headers=auth
    )
    assert published.status_code == 409, published.text
    initial = {
        "scope_id": str(scope_id),
        "effective_from": "2091-01-01",
        "change_reason": "Next",
        "numeric_defaults": [
            {"dimension": "COUNT", "quantity_decimal_places": 0, "quantity_increment": "1"}
        ],
    }
    created = await client.post(drafts, headers=command_headers(auth), json=initial)
    assert created.status_code == 201, created.text
    draft_id = uuid.UUID(created.json()["id"])
    path = drafts + f"/{draft_id}"
    replacement = [
        {"dimension": "TIME", "quantity_decimal_places": 2, "quantity_increment": "0.25"}
    ]
    updated = await client.patch(
        path,
        headers=command_headers(auth),
        json={"expected_version": 1, "numeric_defaults": replacement},
    )
    assert updated.status_code == 200, updated.text
    assert [row["dimension"] for row in updated.json()["numeric_defaults"]] == ["TIME"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(
                await db.scalars(
                    select(ProductNumericDefault.dimension).where(
                        ProductNumericDefault.draft_id == draft_id
                    )
                )
            ) == ["TIME"]
            state = await db.scalar(
                select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
            )
            assert state is not None
            state_id = state.id

    async def token() -> dict[str, Any]:
        response = await client.get(path + "/preview", headers=auth)
        assert response.status_code == 200, response.text
        value = response.json()
        return {
            "expected_version": value["draft_version"],
            "expected_generation": value["policy_generation"],
            "expected_source_version": value["source_version"],
        }

    for field in ("expected_source_version", "expected_generation"):
        body = await token()
        body[field] += 1
        response = await client.post(path + "/publish", headers=command_headers(auth), json=body)
        assert response.status_code == 409 and "stale" in response.text, response.text
    async with changed(
        factory, tenant_a, ProductConfigurationDraft, draft_id, row_version=2147483647
    ):
        response = await client.patch(
            path,
            headers=command_headers(auth),
            json={"expected_version": 2147483647, "change_reason": "Overflow"},
        )
        assert response.status_code == 409 and "exhausted" in response.text, response.text
    for values, message in (
        ({"latest_revision": 2147483647}, "exhausted"),
        ({"row_version": 2147483647}, "exhausted"),
    ):
        async with changed(factory, tenant_a, ProductConfigurationScope, scope_id, **values):
            response = await client.post(
                path + "/publish", headers=command_headers(auth), json=await token()
            )
            assert response.status_code == 409 and message in response.text, response.text
    async with changed(
        factory, tenant_a, CatalogPolicyState, state_id, generation=9223372036854775807
    ):
        response = await client.post(drafts, headers=command_headers(auth), json=initial)
        assert (
            response.status_code == 409 and "generation exhausted" in response.text
        ), response.text
    for date, message in (("2000-01-01", "past defaults"), ("2090-01-01", "advance the effective")):
        import datetime as dt

        async with changed(
            factory,
            tenant_a,
            ProductConfigurationDraft,
            draft_id,
            effective_from=dt.date.fromisoformat(date),
        ):
            response = await client.post(
                path + "/publish", headers=command_headers(auth), json=await token()
            )
            assert response.status_code == 409 and message in response.text, response.text
    published = await client.post(
        path + "/publish", headers=command_headers(auth), json=await token()
    )
    assert published.status_code == 201, published.text
    assert published.json()["revision"] == 2
    # Ascending keyset history remains complete when the last page is exhausted.
    history = scopes + f"/{scope_id}/revisions"
    page = await client.get(history, headers=auth, params={"limit": 1})
    assert page.status_code == 200, page.text
    cursor = page.json()["page"]["next_cursor"]
    assert cursor
    next_page = await client.get(history, headers=auth, params={"limit": 1, "cursor": cursor})
    assert next_page.status_code == 200, next_page.text
    assert next_page.json()["items"][0]["id"] == published.json()["id"]
    assert next_page.json()["page"]["next_cursor"] is None
    invalid = await client.get(
        history, headers=auth, params={"limit": 1, "cursor": cursor + "corrupt"}
    )
    assert invalid.status_code == 422, invalid.text
    for route in (scopes, scopes + f"/{scope_id}/drafts", history):
        invalid = await client.get(route, headers=auth, params={"q": "not-supported"})
        assert invalid.status_code == 422, invalid.text
