"""UI-shaped payloads through native classification, family, SKU and setup routes."""

import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS

from tests.commercial_factories import reference_data
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_all_eight_master_workflows(client, factory, tenant_a):
    company, user, _, initial = await setup_product(factory, tenant_a)
    await reference_data(factory)
    current = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"

    async def create(resource, body):
        receipt = command_headers(current)
        response = await client.post(root + "/" + resource, headers=receipt, json=body)
        assert response.status_code == 201, response.text
        replay = await client.post(root + "/" + resource, headers=receipt, json=body)
        assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
        return response.json()

    brand = await create("brands", {"code": "BASIC", "name": "Basic brand"})
    series = await create(
        "brand-series", {"code": "LINE", "name": "Basic line", "brand_id": brand["id"]}
    )
    producer = await create("manufacturers", {"code": "PRODUCER", "name": "Producer"})
    site = await create(
        "manufacturer-sites",
        {
            "code": "PUNE",
            "name": "Pune site",
            "manufacturer_id": producer["id"],
            "country_code": "IN",
            "state_code": "IN-MH",
        },
    )
    scheme = await create(
        "category-schemes", {"code": "RANGE", "name": "Product range", "membership_mode": "SINGLE"}
    )
    category = await create(
        "item-categories",
        {"code": "BASIC", "name": "Basic category", "scheme_id": scheme["id"], "parent_id": None},
    )
    product_type = await create(
        "product-types", {"code": "BASIC", "name": "Basic product type", "kind": "GOODS"}
    )
    revisions = root + "/product-types/" + product_type["id"] + "/revisions"
    payload = {
        "inventory_modes": ["NON_STOCK"],
        "tracking_modes": ["NONE"],
        "unit_dimensions": ["COUNT"],
        "allow_variants": True,
        "require_brand": False,
        "require_manufacturer": False,
        "require_expiry": False,
    }
    revision = await client.post(revisions, headers=command_headers(current), json=payload)
    assert revision.status_code == 201, revision.text
    revised = await client.patch(
        revisions + "/" + revision.json()["id"],
        headers=command_headers(current),
        json={"expected_version": 1, "require_brand": True},
    )
    assert revised.status_code == 200, revised.text
    publication = await client.post(
        revisions + "/" + revision.json()["id"] + "/publish",
        headers=command_headers(current),
        json={"expected_version": 2},
    )
    assert publication.status_code == 200, publication.text
    choice = await client.get(
        root + "/product-configuration/options/product-type-revisions",
        headers=current,
        params={"value": revision.json()["id"], "kind": "GOODS", "limit": 1},
    )
    assert choice.status_code == 200 and len(choice.json()["items"]) == 1, choice.text
    assert choice.json()["items"][0]["parent_id"] == product_type["id"]
    family = await create(
        "product-families",
        {
            **initial,
            "product_type_revision_id": revision.json()["id"],
            "brand_id": brand["id"],
            "series_id": series["id"],
            "description": "Product family",
            "default_item": {
                **initial["default_item"],
                "sellable": True,
                "purchasable": True,
                "min_sale_quantity": "1.0000",
            },
        },
    )
    family_id, item_id = family["family"]["id"], family["default_item"]["id"]
    for resource, object_id in (("product-families", family_id), ("items", item_id)):
        patch = await client.patch(
            root + "/" + resource + "/" + object_id,
            headers=command_headers(current),
            json={"expected_version": 1, "name": "Updated product"},
        )
        assert patch.status_code == 200 and patch.json()["row_version"] == 2, patch.text

    async def owner_version(resource, object_id):
        detail = await client.get(root + "/" + resource + "/" + object_id, headers=current)
        assert detail.status_code == 200, detail.text
        return detail.json()["row_version"]

    assignments = [
        (
            "categories",
            "PUT",
            {
                "categories": [
                    {"scheme_id": scheme["id"], "category_id": category["id"], "is_primary": True}
                ],
                "valid_from": "2026-10-25",
            },
        ),
        (
            "manufacturers",
            "POST",
            {
                "manufacturer_id": producer["id"],
                "site_id": site["id"],
                "role": "MANUFACTURER",
                "valid_from": "2026-10-25",
                "valid_to": None,
            },
        ),
    ]
    for action, method, body in assignments:
        response = await client.request(
            method,
            root + "/product-families/" + family_id + "/" + action,
            headers=command_headers(current),
            json={"expected_version": await owner_version("product-families", family_id), **body},
        )
        assert response.status_code == 200, response.text
        listing = await client.get(
            root + "/product-families/" + family_id + "/" + action,
            headers=current,
            params={"sort": "id", "limit": 128, "as_of": "2026-10-25"},
        )
        assert listing.status_code == 200 and len(listing.json()["items"]) == 1, listing.text
    binding = await client.post(
        root + "/items/" + item_id + "/unit-bindings",
        headers=command_headers(current),
        json={
            "expected_version": await owner_version("items", item_id),
            "code": "BASE",
            "unit_id": initial["default_item"]["base_unit_id"],
            "role": "BASE",
            "pack_type_id": None,
            "conversion_mode": "FIXED",
            "numerator": "1",
            "denominator": "1",
            "nominal_ratio": None,
            "secondary_unit_id": None,
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "fractional_entry": False,
            "valid_from": "2026-10-25",
        },
    )
    assert binding.status_code == 200, binding.text
    barcode = await client.post(
        root + "/items/" + item_id + "/barcodes",
        headers=command_headers(current),
        json={
            "expected_version": await owner_version("items", item_id),
            "binding_id": None,
            "value": "BASIC001",
            "symbology": "CODE128",
        },
    )
    assert barcode.status_code == 200, barcode.text
    readiness = await client.get(
        root + "/items/" + item_id + "/requirements",
        headers=current,
        params={"as_of": "2026-10-25"},
    )
    assert readiness.status_code == 200 and readiness.json()["item_id"] == item_id, readiness.text
    review = await client.post(
        root + "/category-schemes/" + scheme["id"] + "/transition-preview",
        headers=current,
        json={
            "expected_version": scheme["row_version"],
            "membership_mode": "MULTIPLE",
            "is_required": False,
            "is_active": True,
        },
    )
    assert review.status_code == 200 and review.json()["eligible"], review.text
    applied = await client.post(
        root + "/category-schemes/" + scheme["id"] + "/transition",
        headers=command_headers(current),
        json={
            "expected_version": scheme["row_version"],
            "membership_mode": "MULTIPLE",
            "is_required": False,
            "is_active": True,
            "preview_token": review.json()["preview_token"],
        },
    )
    assert applied.status_code == 200, applied.text


async def test_published_attribute_templates_in_configuration_options(client, factory, tenant_a):
    company, user, _, _ = await setup_product(factory, tenant_a)
    current = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    template = await client.post(
        root + "/attribute-sets",
        headers=command_headers(current),
        json={"code": "SPECS", "name": "Specifications"},
    )
    assert template.status_code == 201, template.text
    route = root + "/attribute-sets/" + template.json()["id"] + "/revisions"
    definition = await client.post(
        root + "/attribute-definitions",
        headers=command_headers(current),
        json={
            "code": "MATERIAL",
            "name": "Material",
            "value_type": "TEXT",
            "is_variant_capable": False,
        },
    )
    assert definition.status_code == 201, definition.text
    draft = await client.post(
        route,
        headers=command_headers(current),
        json={"members": [{"definition_id": definition.json()["id"], "position": 0}]},
    )
    assert draft.status_code == 201, draft.text
    options = root + "/product-configuration/options/attribute-set-revisions"
    assert (await client.get(options, headers=current)).json()["items"] == []
    published = await client.post(
        route + "/" + draft.json()["id"] + "/publish",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    available = await client.get(
        options, headers=current, params={"value": draft.json()["id"], "limit": 1}
    )
    assert (
        available.status_code == 200 and available.json()["items"][0]["value"] == draft.json()["id"]
    ), available.text
    assert available.json()["items"][0]["parent_id"] == template.json()["id"]
