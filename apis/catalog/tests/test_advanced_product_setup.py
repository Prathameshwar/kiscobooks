"""Advanced per-SKU native setup, progress and rollback."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select

from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.pricing import ItemPrice, ItemPriceDraft, ItemReferenceCost
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item, ProductFamily
from tests.attribute_factories import seed_attributes
from tests.pricing_factories import create
from tests.test_advanced_product_definition import prepared
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def definition(client, factory, tenant, *, kind="GOODS"):
    company, user, _, base, body = await prepared(client, factory, tenant, kind=kind)
    auth = headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS))
    result = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert result.status_code == 201, result.text
    return company, auth, base, body, result.json()


def setup_body(body, created):
    return {
        "expected_creation_version": created["creation"]["row_version"],
        "expected_family_version": created["family"]["row_version"],
        "expected_item_version": created["skus"][0]["row_version"],
        "setup": {
            "effective_from": body["as_of"],
            "units": [
                {
                    "expected_version": 1,
                    "code": "BASE",
                    "unit_id": body["skus"][0]["item"]["base_unit_id"],
                    "role": "BASE",
                    "conversion_mode": "FIXED",
                    "numerator": "1",
                    "denominator": "1",
                    "quantity_decimal_places": 0,
                    "quantity_increment": "1",
                    "fractional_entry": False,
                    "valid_from": body["as_of"],
                }
            ],
        },
    }


async def test_setup_replay_progress_and_readiness(client, factory, tenant_a):
    _, auth, base, body, created = await definition(client, factory, tenant_a)
    item = created["skus"][0]["id"]
    path = base + "/definitions/" + created["creation"]["id"] + "/skus/" + item
    request = setup_body(body, created)
    key = str(uuid7())
    signed = {**auth, "Idempotency-Key": key}
    saved = await client.post(path + "/setup", headers=signed, json=request)
    assert saved.status_code == 200, saved.text
    assert saved.json()["sku_progress"][0]["setup_done"] is True
    replay = await client.post(path + "/setup", headers=signed, json=request)
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemUnitBinding.id))) == 1
            assert await db.scalar(select(func.count(ItemUnitRevision.id))) == 1
    readiness = await client.post(path + "/readiness", headers=auth, json={"as_of": body["as_of"]})
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["item_id"] == item
    assert all(entry["path"] for entry in readiness.json()["blockers"])


async def test_invalid_setup_rolls_back_and_recovery_works(client, factory, tenant_a):
    _, auth, base, body, created = await definition(client, factory, tenant_a)
    item = created["skus"][0]["id"]
    path = base + "/definitions/" + created["creation"]["id"] + "/skus/" + item
    request = setup_body(body, created)
    request["setup"]["units"][0]["numerator"] = "2"
    rejected = await client.post(
        path + "/setup", headers={**auth, "Idempotency-Key": str(uuid7())}, json=request
    )
    assert rejected.status_code in {409, 422}, rejected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(ItemUnitBinding.id)) is None
    status = await client.get(base + "/definitions/" + created["creation"]["id"], headers=auth)
    assert status.status_code == 200 and status.json()["sku_progress"][0]["setup_done"] is False
    request["setup"]["units"][0]["numerator"] = "1"
    recovered = await client.post(
        path + "/setup", headers={**auth, "Idempotency-Key": str(uuid7())}, json=request
    )
    assert recovered.status_code == 200, recovered.text


async def test_price_and_purchase_reference_publish_with_exact_values(client, factory, tenant_a):
    company, user, _, base, body = await prepared(client, factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    level = await create(client, root, auth, "/pricing/bootstrap", {})
    plan = await create(
        client,
        root,
        auth,
        "/price-plans",
        {
            "code": "ADVANCED_SALE",
            "name": "Advanced sale",
            "purpose": "SALE",
            "price_level_id": level["id"],
            "currency": "INR",
            "tax_basis": "EXCLUSIVE",
        },
    )
    options = await client.get(base + "/options?kind=GOODS", headers=auth)
    assert options.status_code == 200, options.text
    reviewed = options.json()
    body["mode_version"] = reviewed["mode"]["row_version"]
    body["policy_generation"] = reviewed["mode"]["policy_generation"]
    body["source_version"] = reviewed["defaults"]["configuration"]["source_version"]
    created_response = await client.post(
        base + "/definitions",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    item = created["skus"][0]["id"]
    path = base + "/definitions/" + created["creation"]["id"] + "/skus/" + item
    current = await client.get(base + "/options?kind=GOODS", headers=auth)
    assert current.status_code == 200, current.text
    policy = current.json()
    request = setup_body(body, created)
    request["setup"].update(
        {
            "expected_generation": policy["mode"]["policy_generation"],
            "expected_source_version": policy["defaults"]["configuration"]["source_version"],
            "prices": [
                {
                    "plan_id": plan["id"],
                    "amount": "123.4500",
                    "price_basis_quantity": "1",
                    "price_decimal_places": 4,
                }
            ],
        }
    )
    request["purchase_reference"] = {
        "amount": "91.2500",
        "price_basis_quantity": "1",
        "currency": "INR",
        "price_decimal_places": 4,
        "estimate_kind": "STANDARD_ESTIMATE",
        "source_reference": "Supplier quotation 42",
    }
    no_cost = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=sorted(CATALOG_PERMISSIONS - {"reference_cost.manage"}),
    )
    denied = await client.post(
        path + "/setup",
        headers={**no_cost, "Idempotency-Key": str(uuid7())},
        json=request,
    )
    assert denied.status_code == 403, denied.text
    saved = await client.post(
        path + "/setup",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=request,
    )
    assert saved.status_code == 200, saved.text
    progress = saved.json()["sku_progress"][0]
    assert len(progress["price_draft_ids"]) == 1
    assert progress["purchase_reference_id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            draft = await db.scalar(
                select(ItemPriceDraft).where(ItemPriceDraft.item_id == uuid.UUID(item))
            )
            cost = await db.scalar(
                select(ItemReferenceCost).where(ItemReferenceCost.item_id == uuid.UUID(item))
            )
            assert draft is not None and str(draft.amount) == "123.4500"
            assert cost is not None and str(cost.amount) == "91.2500"
    publication_key = str(uuid7())
    publication_body = {"expected_creation_version": saved.json()["row_version"]}
    published = await client.post(
        path + "/publish-prices",
        headers={**auth, "Idempotency-Key": publication_key},
        json=publication_body,
    )
    assert published.status_code == 200, published.text
    assert len(published.json()["sku_progress"][0]["published_price_ids"]) == 1
    replay = await client.post(
        path + "/publish-prices",
        headers={**auth, "Idempotency-Key": publication_key},
        json=publication_body,
    )
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPrice.id))) == 1


async def test_service_readiness_blocks_incomplete_profile_and_tax(client, factory, tenant_a):
    _, auth, base, body, created = await definition(client, factory, tenant_a, kind="SERVICE")
    item = created["skus"][0]["id"]
    path = base + "/definitions/" + created["creation"]["id"] + "/skus/" + item
    saved = await client.post(
        path + "/setup",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=setup_body(body, created),
    )
    assert saved.status_code == 200, saved.text
    readiness = await client.post(path + "/readiness", headers=auth, json={"as_of": body["as_of"]})
    assert readiness.status_code == 200, readiness.text
    ready = readiness.json()
    assert ready["eligible"] is False
    assert {entry["path"] for entry in ready["blockers"]} >= {
        "profile.group_id",
        "business.skus.0.tax",
    }
    activation = await client.post(
        path + "/activate",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_creation_version": saved.json()["row_version"],
            "expected_family_version": ready["family_version"],
            "expected_item_version": ready["item_version"],
            "as_of": body["as_of"],
            "expected_generation": ready["policy_generation"],
            "expected_source_version": ready["source_version"],
        },
    )
    assert activation.status_code == 409, activation.text
    current = await client.get(base + "/definitions/" + created["creation"]["id"], headers=auth)
    assert current.status_code == 200 and current.json()["sku_progress"][0]["activated"] is False


async def test_tax_reference_change_rolls_back_setup(client, factory, tenant_a):
    _, auth, base, body, created = await definition(client, factory, tenant_a)
    item = created["skus"][0]["id"]
    path = base + "/definitions/" + created["creation"]["id"] + "/skus/" + item
    options = await client.get(base + "/options?kind=GOODS", headers=auth)
    assert options.status_code == 200, options.text
    request = setup_body(body, created)
    request["setup"].update(
        {
            "expected_generation": options.json()["mode"]["policy_generation"],
            "expected_source_version": options.json()["defaults"]["configuration"][
                "source_version"
            ],
            "tax": {"rule_id": str(uuid.uuid4()), "directions": ["SALE"]},
        }
    )
    rejected = await client.post(
        path + "/setup", headers={**auth, "Idempotency-Key": str(uuid7())}, json=request
    )
    assert rejected.status_code in {403, 404, 409}, rejected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(ItemUnitBinding.id)) is None
    current = await client.get(base + "/definitions/" + created["creation"]["id"], headers=auth)
    assert current.status_code == 200 and current.json()["sku_progress"][0]["setup_done"] is False


async def test_variant_skus_keep_independent_setup_progress(client, factory, tenant_a):
    company, user, _, base, body = await prepared(client, factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    records = await seed_attributes(factory, tenant_a, company)
    definition_id = str(records["attribute_definition"])
    blue = str(records["attribute_option"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            from catalog.domain.attributes import AttributeValue
            from catalog.models.attributes import AttributeOption

            digest, canonical = AttributeValue("TEXT", "Red").canonical()
            red = AttributeOption(
                tenant_id=tenant_a,
                company_id=company,
                definition_id=records["attribute_definition"],
                code="RED",
                name="Red",
                value_type="TEXT",
                value_text="Red",
                value_hash=digest,
                canonical_value=canonical,
            )
            db.add(red)
            await db.flush()
            red_id = str(red.id)
    body["attributes"] = [
        {
            "definition_id": definition_id,
            "is_axis": True,
            "is_required": True,
            "position": 0,
            "options": [blue, red_id],
        }
    ]
    body["skus"][0]["attributes"] = [
        {"definition_id": definition_id, "option_id": blue, "value_type": "TEXT"}
    ]
    body["skus"].append(
        {
            "item": {
                "sku": "RED-SKU",
                "name": "Red product",
                "base_unit_id": body["skus"][0]["item"]["base_unit_id"],
            },
            "attributes": [
                {"definition_id": definition_id, "option_id": red_id, "value_type": "TEXT"}
            ],
        }
    )
    created_response = await client.post(
        base + "/definitions",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    base_path = base + "/definitions/" + created["creation"]["id"] + "/skus/"
    first = await client.post(
        base_path + created["skus"][0]["id"] + "/setup",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=setup_body(body, created),
    )
    assert first.status_code == 200, first.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            receipt = await db.get(AdvancedProductCreation, uuid.UUID(created["creation"]["id"]))
            family = await db.get(ProductFamily, uuid.UUID(created["family"]["id"]))
            first_item = await db.get(Item, uuid.UUID(created["skus"][0]["id"]))
            assert receipt is not None and family is not None and first_item is not None
            family.status, family.row_version = "ACTIVE", family.row_version + 1
            first_item.status = "ACTIVE"
            progress = dict(receipt.progress)
            entries = dict(progress["skus"])
            first_progress = dict(entries[created["skus"][0]["id"]])
            first_progress["activated"] = True
            entries[created["skus"][0]["id"]] = first_progress
            progress["skus"] = entries
            receipt.progress = progress
            receipt.status, receipt.step = "ACTIVATING", "ACTIVATE"
            receipt.row_version += 1
    second_body = setup_body(body, created)
    second_body["expected_creation_version"] = first.json()["row_version"] + 1
    second_body["expected_family_version"] = created["family"]["row_version"] + 1
    second_body["expected_item_version"] = created["skus"][1]["row_version"]
    second_body["setup"]["units"][0]["numerator"] = "2"
    second_path = base_path + created["skus"][1]["id"] + "/setup"
    rejected = await client.post(
        second_path,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=second_body,
    )
    assert rejected.status_code in {409, 422}, rejected.text
    status = await client.get(base + "/definitions/" + created["creation"]["id"], headers=auth)
    assert status.status_code == 200, status.text
    assert [entry["setup_done"] for entry in status.json()["sku_progress"]] == [True, False]
    second_body["setup"]["units"][0]["numerator"] = "1"
    recovered = await client.post(
        second_path,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=second_body,
    )
    assert recovered.status_code == 200, recovered.text
    assert [entry["setup_done"] for entry in recovered.json()["sku_progress"]] == [True, True]
    assert recovered.json()["status"] == "ACTIVATING"
