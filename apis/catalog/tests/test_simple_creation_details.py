"""Configured details participate in the native single-Save creation transaction."""

import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from catalog.models.configuration import ProductEntryOptionPolicy
from catalog.models.product_definitions import ItemBarcode
from catalog.models.products import Item
from tests.conftest import ACTOR_SECRET
from tests.test_master_reference_policy import policy
from tests.test_simple_product_creation import finish, starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def barcode_policy(factory, tenant, mode):
    with tenant_scope(tenant):
        async with factory.begin() as db:
            row = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            row.barcode_mode = mode
            row.barcode_default = False if mode == "OPTIONAL" else None


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_required_barcode_creates_active_product_and_replays_once(
    client, factory, tenant_a, kind
):
    root, auth, unit = await starter(factory, tenant_a)
    await barcode_policy(factory, tenant_a, "REQUIRED")
    options = await client.get(
        root + "/simple-product-creations/options", headers=auth, params={"kind": kind}
    )
    assert options.status_code == 200, options.text
    fields = {row["key"]: row for row in options.json()["fields"]}
    assert fields["barcode_value"]["writable"]
    assert {row["value"] for row in fields["barcode_symbology"]["control"]["choices"]} == {
        "CODE128",
        "GTIN",
        "QR",
    }
    body = {"name": "Barcoded product", "kind": kind, "base_unit_id": unit}
    missing = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert missing.status_code == 422, missing.text
    assert "barcode.value" in missing.json()["error"]["fields"]
    body["barcode"] = {"value": "0012345678905", "symbology": "GTIN"}
    signed = auth | {"Idempotency-Key": str(uuid7())}
    started = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert started.status_code == 201, started.text
    done = await finish(client, root, auth, started.json()["id"])
    replay = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == done["id"], replay.text
    product = await client.get(root + "/products/" + done["item_id"], headers=auth)
    assert product.status_code == 200 and product.json()["status"] == "ACTIVE", product.text
    duplicate = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body | {"name": "Duplicate barcode"},
    )
    assert duplicate.status_code == 201, duplicate.text
    rejected = await client.post(
        root + "/simple-product-creations/" + duplicate.json()["id"] + "/advance",
        headers=auth,
    )
    assert rejected.status_code == 409, rejected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            rows = list(await db.scalars(select(ItemBarcode)))
            assert len(rows) == 1 and rows[0].value == "0012345678905" and rows[0].is_active
            assert str(rows[0].item_id) == done["item_id"]
            assert await db.scalar(select(func.count(Item.id))) == 1


@pytest.mark.parametrize("mode,value", [("DISABLED", "CODE-1"), ("OPTIONAL", "0012345678900")])
async def test_barcode_disabled_or_invalid_is_rejected_before_creation(
    client, factory, tenant_a, mode, value
):
    root, auth, unit = await starter(factory, tenant_a)
    await barcode_policy(factory, tenant_a, mode)
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "name": "Invalid barcode",
            "base_unit_id": unit,
            "barcode": {"value": value, "symbology": "GTIN" if mode == "OPTIONAL" else "CODE128"},
        },
    )
    assert response.status_code == 422, response.text
    assert "barcode.value" in response.json()["error"]["fields"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemBarcode.id))) == 0


@pytest.mark.parametrize("access,field", [("write", "value"), ("read", "symbology")])
async def test_barcode_field_permissions_are_preserved(client, factory, tenant_a, access, field):
    root, auth, unit = await starter(factory, tenant_a)
    await barcode_policy(factory, tenant_a, "OPTIONAL")
    context = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    await policy(
        factory,
        tenant_a,
        context.company_id,
        context.user_id,
        "catalog.item_barcode",
        field,
        access,
    )
    options = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert options.status_code == 200, options.text
    protected = next(
        (row for row in options.json()["fields"] if row["key"] == "barcode_" + field), None
    )
    if access == "write":
        assert protected is not None and not protected["writable"]
    else:
        assert protected is None or not protected["visible"]
    started = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={"name": "Protected barcode", "base_unit_id": unit, "barcode": {"value": "ABC123"}},
    )
    assert started.status_code == 201, started.text
    advanced = await client.post(
        root + "/simple-product-creations/" + started.json()["id"] + "/advance", headers=auth
    )
    if access == "read":
        # Native read and write permissions are independent. A permitted blind
        # write must still omit protected fields from metadata and later reads.
        assert advanced.status_code == 200, advanced.text
        listed = await client.get(
            root + "/items/" + advanced.json()["item_id"] + "/barcodes", headers=auth
        )
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["items"]) == 1
        assert field not in listed.json()["items"][0]
        return
    assert advanced.status_code == 403, advanced.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
            assert await db.scalar(select(func.count(ItemBarcode.id))) == 0


def test_barcode_addition_preserves_older_creation_hashes():
    from catalog.schemas.simple_product_creation import SimpleCreationBarcode, SimpleCreationInput
    from catalog.tasks.simple_product_creation import creation_request

    body = SimpleCreationInput(name="Existing command", base_unit_id=uuid7())
    old = body.model_dump(
        mode="json",
        exclude={
            "barcode", "sale_prices", "categories", "manufacturer_id", "manufacturer_site_id",
            "batch_enabled", "batches", "serials",
        },
    )
    assert creation_request(body) == old
    with_barcode = body.model_copy(update={"barcode": SimpleCreationBarcode(value="0000123")})
    assert creation_request(with_barcode) == old | {
        "barcode": {"value": "0000123", "symbology": "CODE128"}
    }


async def test_simple_import_template_supports_required_barcode(client, factory, tenant_a):
    root, auth, _ = await starter(factory, tenant_a)
    await barcode_policy(factory, tenant_a, "REQUIRED")
    response = await client.post(
        root + "/import-templates",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "definition": "simple_products",
            "parameters": {"resource": "simple_product_create", "kind": "GOODS"},
        },
    )
    assert response.status_code == 201, response.text
    schema = response.json()["snapshot"]["schemas"]["simple_product_create:CREATE"]
    assert "barcode_value" in schema["required"]
    assert "barcode_symbology" in schema["properties"]
