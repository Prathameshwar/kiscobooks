"""Specifications and ordinary setup remain independent of variant authoring."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select

from catalog.models import FamilyAttribute, ItemAttributeValue
from tests.attribute_factories import seed_attributes
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_product_initial_setup import initial
from tests.test_product_mode import set_mode
from tests.test_simple_products import simple_input

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_simple_specs_work_but_axes_are_blocked(client, factory, tenant_a):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    ids = await seed_attributes(factory, tenant_a, company)
    root = f"/v1/companies/{company}"
    created = await client.post(
        root + "/products", headers=command_headers(auth), json=simple_input(legacy)
    )
    assert created.status_code == 201, created.text
    product = created.json()
    field = {
        "definition_id": str(ids["attribute_definition"]),
        "is_axis": False,
        "is_required": True,
        "position": 0,
        "options": [str(ids["attribute_option"])],
    }
    value = {
        "definition_id": field["definition_id"],
        "value_type": "TEXT",
        "option_id": str(ids["attribute_option"]),
    }
    # The option-backed definition determines its native value type; inspect the fixture.
    from catalog.models.attributes import AttributeDefinition

    with tenant_scope(tenant_a):
        async with factory() as db:
            definition = await db.get(AttributeDefinition, ids["attribute_definition"])
            value["value_type"] = definition.value_type
    path = root + "/products/" + product["id"] + "/attributes"
    request = {
        "revision": product["revision"],
        "authoring_version": 0,
        "attributes": [field],
        "values": [value],
    }
    changed = await client.put(path, headers=command_headers(auth), json=request)
    assert changed.status_code == 200, changed.text
    product = changed.json()
    form = await client.get(root + "/items/" + product["id"] + "/attribute-form", headers=auth)
    assert form.status_code == 200, form.text
    assert form.json()["fields"][0]["writable"] is True
    assert form.json()["can_create_variant"] is False
    blocked = await client.put(
        path,
        headers=command_headers(auth),
        json={
            **request,
            "revision": product["revision"],
            "attributes": [{**field, "is_axis": True}],
        },
    )
    assert blocked.status_code == 409, blocked.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemAttributeValue.id))) == 1
            assert await db.scalar(select(FamilyAttribute.is_axis)) is False
    enabled, _, _ = await set_mode(client, company, auth, True)
    assert enabled.status_code == 200, enabled.text
    allowed = await client.put(
        path,
        headers=command_headers(auth),
        json={
            **request,
            "revision": product["revision"],
            "authoring_version": enabled.json()["row_version"],
            "attributes": [{**field, "is_axis": True}],
        },
    )
    assert allowed.status_code == 200, allowed.text
    disabled, _, _ = await set_mode(client, company, auth, False)
    assert disabled.status_code == 409, disabled.text


async def test_simple_initial_units_and_single_metadata(client, factory, tenant_a):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    metadata = await client.get(
        root + "/products/field-set", headers=auth, params={"operation": "create"}
    )
    assert metadata.status_code == 200, metadata.text
    keys = [field["key"] for field in metadata.json()["fields"]]
    assert keys.count("code") == keys.count("name") == 1
    assert "sku" not in keys and "family_id" not in keys
    status = next(field for field in metadata.json()["fields"] if field["key"] == "status")
    assert status["visible"] and not status["writable"]
    body = {**simple_input(legacy), "initial_setup": initial(legacy)}
    created = await client.post(root + "/products", headers=command_headers(auth), json=body)
    assert created.status_code == 201, created.text
    native = await client.get(root + "/items/" + created.json()["id"], headers=auth)
    assert native.status_code == 200, native.text
    assert native.json()["id"] == created.json()["id"]
    editable = await client.get(
        root + "/products/field-set",
        headers=auth,
        params={"operation": "update", "object_id": created.json()["id"]},
    )
    assert editable.status_code == 200, editable.text
    writable = {field["key"]: field["writable"] for field in editable.json()["fields"]}
    assert writable["code"] and writable["name"]
    assert not writable["base_unit_id"] and not writable["kind"]
    assert not writable["product_type_revision_id"]
    assert not writable["status"]
    from catalog.models import ItemUnitBinding

    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(func.count(ItemUnitBinding.id)).where(
                        ItemUnitBinding.item_id == uuid.UUID(created.json()["id"])
                    )
                )
                == 1
            )
    await policy(factory, tenant_a, company, user, "catalog.item", "status", "read")
    protected = await client.get(root + "/products/field-set", headers=auth)
    assert protected.status_code == 200, protected.text
    assert "status" not in {field["key"] for field in protected.json()["fields"]}
    forbidden = await client.get(root + "/products", headers=auth, params={"status": "DRAFT"})
    assert forbidden.status_code == 403, forbidden.text


async def test_simple_aggregate_checks_both_native_field_denies(client, factory, tenant_a):
    company, user, auth, legacy = await setup_product(factory, tenant_a, advanced=False)
    root = f"/v1/companies/{company}/products"
    created = await client.post(root, headers=command_headers(auth), json=simple_input(legacy))
    assert created.status_code == 201, created.text
    await policy(factory, tenant_a, company, user, "catalog.product_family", "name", "write")
    result = await client.patch(
        root + "/" + created.json()["id"],
        headers=command_headers(auth),
        json={"revision": created.json()["revision"], "authoring_version": 0, "name": "Denied"},
    )
    assert result.status_code == 403, result.text
    unchanged = await client.get(root + "/" + created.json()["id"], headers=auth)
    assert unchanged.json()["name"] == "Product"


async def test_simple_custom_fields_keep_native_owners_and_preserve_omitted_values(
    client, factory, tenant_a
):
    from tests.test_product_custom_fields import install

    company, user, auth, legacy = await setup_product(factory, tenant_a, advanced=False)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {"entity_type": "catalog.item", "data_type": "text"},
            {"entity_type": "catalog.product_family", "data_type": "text"},
        ],
    )
    root = f"/v1/companies/{company}/products"
    created = await client.post(
        root,
        headers=command_headers(auth),
        json={
            **simple_input(legacy),
            "custom_fields": {"cf_note": "Item note"},
            "shared_custom_fields": {"cf_note": "Shared note"},
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["custom_fields"]["cf_note"] == "Item note"
    assert product["shared_custom_fields"]["cf_note"] == "Shared note"
    changed = await client.patch(
        root + "/" + product["id"],
        headers=command_headers(auth),
        json={
            "revision": product["revision"],
            "authoring_version": 0,
            "custom_fields": {"cf_note": "Updated item note"},
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["custom_fields"]["cf_note"] == "Updated item note"
    assert changed.json()["shared_custom_fields"]["cf_note"] == "Shared note"
    metadata = await client.get(root + "/field-set", headers=auth, params={"operation": "create"})
    assert metadata.status_code == 200, metadata.text
    assert {field["key"] for field in metadata.json()["fields"]} >= {
        "custom_fields.cf_note",
        "shared_custom_fields.cf_note",
    }


async def test_simple_category_preview_and_commit_use_one_product_revision(
    client, factory, tenant_a
):
    from billing_platform.ids import uuid7

    from catalog.models import CategoryScheme, ItemCategory

    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            scheme = CategoryScheme(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=company,
                code="CATEGORY",
                name="Category",
                membership_mode="SINGLE",
            )
            db.add(scheme)
            await db.flush()
            category = ItemCategory(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=company,
                code="NOTEBOOK",
                name="Notebooks",
                scheme_id=scheme.id,
            )
            db.add(category)
    root = f"/v1/companies/{company}/products"
    created = await client.post(root, headers=command_headers(auth), json=simple_input(legacy))
    assert created.status_code == 201, created.text
    product = created.json()
    request = {
        "revision": product["revision"],
        "authoring_version": 0,
        "categories": [
            {"scheme_id": str(scheme.id), "category_id": str(category.id), "is_primary": True}
        ],
    }
    preview = await client.post(
        root + "/" + product["id"] + "/category-preview", headers=auth, json=request
    )
    assert preview.status_code == 200, preview.text
    assert "family_id" not in preview.json()
    saved = await client.put(
        root + "/" + product["id"] + "/categories",
        headers=command_headers(auth),
        json={**request, "preview_token": preview.json()["preview_token"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["id"] == product["id"]


async def test_simple_manufacturer_rejects_reversed_dates_before_command(client, factory, tenant_a):
    from billing_platform.ids import uuid7

    company, _, auth, _ = await setup_product(factory, tenant_a, advanced=False)
    response = await client.post(
        f"/v1/companies/{company}/products/{uuid7()}/manufacturers",
        headers=command_headers(auth),
        json={
            "revision": "unused",
            "authoring_version": 0,
            "manufacturer_id": str(uuid7()),
            "valid_from": "2050-01-02",
            "valid_to": "2050-01-01",
        },
    )
    assert response.status_code == 422, response.text
