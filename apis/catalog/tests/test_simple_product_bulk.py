"""Simple import identities and reviewed aggregate updates use native bulk workers."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select

from catalog.models import Item, ProductFamily
from tests.bulk_factories import post, run
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_bulk_products_prices import reviewed_commit
from tests.test_product_mode import set_mode
from tests.test_simple_products import simple_input

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_simple_bulk_creates_and_updates_one_product(client, factory, tenant_a):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    data = simple_input(legacy)
    data.pop(
        "authoring_version"
    )  # Prepared by the native import adapter, not a spreadsheet column.
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "records": [
                {
                    "key": "product",
                    "change_set": "product",
                    "resource": "simple_product",
                    "data": data,
                }
            ],
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.scalar(select(Item).where(Item.company_id == company))
            assert item is not None
            item_id = str(item.id)
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "edit",
                    "change_set": "edit",
                    "resource": "simple_product",
                    "action": "UPDATE",
                    "target": {"code": data["code"]},
                    "data": {"name": "Imported product name"},
                }
            ],
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.get(Item, uuid.UUID(item_id))
            family = await db.get(ProductFamily, item.family_id)
            assert item.name == family.name == "Imported product name"


async def test_simple_bulk_dependent_edit_resolves_created_item(client, factory, tenant_a):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    data = simple_input(legacy)
    data.pop("authoring_version")
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "records": [
                {
                    "key": "product",
                    "change_set": "product",
                    "resource": "simple_product",
                    "data": data,
                },
                {
                    "key": "edit",
                    "change_set": "product",
                    "resource": "simple_product",
                    "action": "UPDATE",
                    "target": {"record": "product", "field": "id"},
                    "depends_on": ["product"],
                    "data": {"description": "Updated through the product ID"},
                },
            ],
        },
    )


async def test_mode_change_invalidates_reviewed_simple_import(client, factory, tenant_a):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}/bulk-jobs"
    data = simple_input(legacy)
    data.pop("authoring_version")
    job = await post(
        client,
        root,
        auth,
        "",
        {
            "format": "JSON",
            "records": [
                {
                    "key": "product",
                    "change_set": "product",
                    "resource": "simple_product",
                    "data": data,
                }
            ],
        },
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    review = (await client.get(root + "/" + job["id"], headers=auth)).json()
    enabled, _, _ = await set_mode(client, company, auth, True)
    assert enabled.status_code == 200, enabled.text
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {"expected_version": review["row_version"], "selection_digest": review["selection_digest"]},
    )
    # The existing job-level generation fence rejects execution before any row
    # starts; it asks for a new review rather than applying a changed command.
    with pytest.raises(ConflictError, match="review again"):
        await run(factory, tenant_a, company, user, job["id"])
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(Item.id).where(Item.company_id == company)) is None


async def test_simple_file_template_and_import_preserve_shared_custom_fields(
    client, factory, tenant_a
):
    from tests.test_master_imports import command, source
    from tests.test_product_custom_fields import install

    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
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
    root = f"/v1/companies/{company}"
    template = await command(
        client, root, auth, "/import-templates", {"definition": "products"}, 201
    )
    snapshot = template["snapshot"]
    assert set(snapshot["schemas"]) == {"simple_product:CREATE", "simple_product:UPDATE"}
    metadata = {field["key"] for field in snapshot["fields"]["simple_product"]}
    assert {"code", "name", "custom_fields.cf_note", "shared_custom_fields.cf_note"} <= metadata
    assert "sku" not in metadata and "family_id" not in metadata
    data = simple_input(legacy)
    data.pop("authoring_version")
    data.update(
        custom_fields={"cf_note": "Item note"}, shared_custom_fields={"cf_note": "Shared note"}
    )
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": template["id"], "files": [source("simple_product", data)]},
        201,
    )
    path = "/import-jobs/" + job["id"]
    reviewed = await command(client, root, auth, path + "/validate", {"expected_version": 1})
    assert reviewed["state"] == "READY", reviewed
    applied = await command(
        client,
        root,
        auth,
        path + "/commit",
        {"expected_version": reviewed["row_version"], "review_digest": reviewed["review_digest"]},
    )
    assert applied["state"] == "SUCCEEDED", applied
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.scalar(select(Item).where(Item.company_id == company))
            family = await db.get(ProductFamily, item.family_id)
            assert item.custom_fields["cf_note"] == "Item note"
            assert family.custom_fields["cf_note"] == "Shared note"
