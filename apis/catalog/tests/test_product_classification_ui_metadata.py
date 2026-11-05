"""Capture native controls and separate product type publication authority."""

import json
from pathlib import Path

import pytest
from billing_platform.ids import uuid7

from tests.test_api import headers
from tests.test_classification_api import setup_source

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
ENTITIES = {
    "product_family": "item",
    "item": "item",
    "product_type": "product_type",
    "product_type_revision": "product_type",
    "category_scheme": "category_scheme",
    "item_category": "item_category",
    "brand": "brand",
    "brand_series": "brand_series",
    "manufacturer_site": "manufacturer_site",
    "family_category": "item",
    "family_group_assignment": "item",
    "family_manufacturer": "item",
    "item_unit_binding": "item",
    "item_unit_revision": "item",
    "item_barcode": "item",
}


async def test_type_publication_metadata(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/entities/catalog.product_type_revision/field-set"
    for verb in ("manage", "publish"):
        current = headers(
            company,
            tenant=tenant_a,
            user=user,
            permission=["product_type.read", "product_type." + verb],
        )
        for operation in ("update", "publish"):
            response = await client.get(route, headers=current, params={"operation": operation})
            assert response.status_code == 200, response.text
            fields = {field["key"]: field for field in response.json()["fields"]}
            assert fields["allow_variants"]["writable"] == (
                verb == ("publish" if operation == "publish" else "manage")
            )
            assert fields["published_at"]["writable"] == (
                verb == "publish" and operation == "publish"
            )


async def test_classification_controls_capture(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            prefix + "." + verb
            for prefix in set(ENTITIES.values())
            for verb in ("read", "create", "update", "activate", "manage", "publish", "move")
        ],
    )
    captured = {}
    for entity in ENTITIES:
        for operation in (
            "read",
            "create",
            "update",
            *(["publish"] if entity == "product_type_revision" else []),
        ):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()["fields"]
    created = {field["key"]: field for field in captured["product_type_revision:create"]}
    assert created["product_type_id"]["writable"]
    assert created["inventory_modes"]["control"]["choices"]
    family = {field["key"]: field for field in captured["product_family:create"]}
    assert (
        family["product_type_revision_id"]["control"]["reference_source"]
        == "product-type-revisions"
    )
    destination = (
        Path(__file__).resolve().parents[3]
        / ".tools/product-classification-review/native-fields.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(captured, indent=2), encoding="utf-8")
