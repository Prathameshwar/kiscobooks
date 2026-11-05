import uuid

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.product_definition_factories import seed_definitions
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_all_definition_detail_and_history_routes_are_protected_and_typed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    other, foreign_ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    foreign = headers(
        other,
        tenant=tenant_a,
        user=foreign_ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS),
    )
    base = f"/v1/companies/{company}"
    resources = (
        ("product-families", "product_family", "groups", "family_group_assignment"),
        ("product-families", "product_family", "categories", "family_category"),
        ("product-families", "product_family", "manufacturers", "family_manufacturer"),
        ("product-families", "product_family", "attributes", "family_attribute"),
        ("product-families", "product_family", "attribute-options", "family_attribute_option"),
        ("items", "item", "attributes", "item_attribute_value"),
        ("items", "item", "unit-bindings", "item_unit_binding"),
        ("items", "item", "barcodes", "item_barcode"),
        ("items", "item", "configuration-adoptions", "product_configuration_adoption"),
        ("item-unit-bindings", "item_unit_binding", "revisions", "item_unit_revision"),
        (
            "product-configuration-adoptions",
            "product_configuration_adoption",
            "sources",
            "product_configuration_adoption_source",
        ),
    )
    for parent, owner, collection, model in resources:
        route = f"/{parent}/{ids[owner]}/{collection}"
        page = await client.get(base + route, headers=auth, params={"sort": "-id", "limit": 1})
        assert page.status_code == 200, page.text
        assert page.json()["items"][0]["id"] == str(ids[model])
        detail = await client.get(base + route + f"/{ids[model]}", headers=auth)
        assert detail.status_code == 200, detail.text
        assert detail.json()["company_id"] == str(company)
        assert (await client.get(base + route + f"/{ids[model]}")).status_code == 401
        crossed = await client.get(
            f"/v1/companies/{other}" + route + f"/{ids[model]}", headers=foreign
        )
        assert crossed.status_code == 403, crossed.text
        invalid = await client.get(base + route, headers=auth, params={"q": "unsupported"})
        assert invalid.status_code == 422, invalid.text
        if model not in {
            "family_group_assignment",
            "family_category",
            "family_manufacturer",
            "item_unit_revision",
        }:
            undated = await client.get(base + route, headers=auth, params={"as_of": "2090-01-01"})
            assert undated.status_code == 422, undated.text
    for path, key in (
        ("product-configuration-scopes", "product_configuration_scope"),
        ("product-configurations", "product_configuration_draft"),
        ("product-configuration-revisions", "product_configuration_revision"),
    ):
        response = await client.get(base + f"/{path}/{ids[key]}", headers=auth)
        assert response.status_code == 200, response.text
        invalid = await client.get(
            base + f"/{path}/{ids[key]}", headers=auth, params={"unexpected": True}
        )
        assert invalid.status_code == 422, invalid.text
    params = {"as_of": "2090-01-01", "kind": "GOODS"}
    result = await client.get(
        base + f"/item-groups/{ids['item_group']}/defaults", headers=auth, params=params
    )
    assert result.status_code == 200, result.text
    disagreement = await client.get(
        base + f"/item-groups/{ids['item_group']}/defaults",
        headers=auth,
        params={**params, "group_id": str(foreign_ids["item_group"])},
    )
    assert disagreement.status_code == 422
    for collection in ("requirements", "configuration"):
        result = await client.get(
            base + f"/items/{ids['item']}/{collection}",
            headers=auth,
            params={"as_of": "2090-01-01"},
        )
        assert result.status_code == 200, result.text
