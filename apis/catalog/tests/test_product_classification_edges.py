import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CategoryScheme,
    FamilyGroupAssignment,
    Manufacturer,
    ManufacturerSite,
    ProductFamily,
)
from tests.commercial_factories import reference_data
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_classification_edges_check_scheme_site_kind_and_historical_dates(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    await reference_data(factory)
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    path = f"/v1/companies/{company}/product-families/{ids['product_family']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            common = {"tenant_id": tenant_a, "company_id": company}
            other = Manufacturer(**common, code="OTHER", name="Other")
            scheme = CategoryScheme(**common, code="OTHER", name="Other", membership_mode="SINGLE")
            db.add_all([other, scheme])
            await db.flush()
            site = ManufacturerSite(
                **common, manufacturer_id=other.id, code="SITE", name="Site", country_code="IN"
            )
            db.add(site)
            await db.flush()
            other_id, site_id, scheme_id = other.id, site.id, scheme.id
    category = await client.put(
        path + "/categories",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "categories": [{"scheme_id": str(scheme_id), "category_id": str(ids["item_category"])}],
        },
    )
    assert category.status_code == 403 and "another scheme" in category.text, category.text
    body = {
        "expected_version": 1,
        "manufacturer_id": str(ids["manufacturer"]),
        "site_id": str(site_id),
        "valid_from": "2091-01-01",
        "role": "IMPORTER",
    }
    site_response = await client.post(
        path + "/manufacturers", headers=command_headers(auth), json=body
    )
    assert (
        site_response.status_code == 403 and "another manufacturer" in site_response.text
    ), site_response.text
    async with changed(factory, tenant_a, ProductFamily, ids["product_family"], kind="SERVICE"):
        rejected = await client.post(
            path + "/manufacturers", headers=command_headers(auth), json=body
        )
        assert rejected.status_code == 422 and "services" in rejected.text, rejected.text
    async with changed(
        factory,
        tenant_a,
        FamilyGroupAssignment,
        ids["family_group_assignment"],
        valid_from=dt.date(2000, 1, 1),
    ):
        rejected = await client.post(
            path + "/groups",
            headers=command_headers(auth),
            json={
                "expected_version": 1,
                "group_id": str(ids["item_group"]),
                "valid_from": "2001-01-01",
            },
        )
        assert (
            rejected.status_code == 409 and "rewrite effective history" in rejected.text
        ), rejected.text
    accepted = await client.post(
        path + "/manufacturers",
        headers=command_headers(auth),
        json={**body, "manufacturer_id": str(other_id)},
    )
    assert accepted.status_code == 200, accepted.text
    cleared = await client.put(
        path + "/categories",
        headers=command_headers(auth),
        json={"expected_version": 2, "categories": []},
    )
    assert cleared.status_code == 200, cleared.text
    assert (await client.get(path + "/categories", headers=auth)).json()["items"] == []
