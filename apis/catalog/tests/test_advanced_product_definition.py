"""Atomic advanced Profile/SKU definition, receipt and scoped recovery."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select

from catalog.domain.attributes import AttributeValue
from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.attributes import AttributeOption
from catalog.models.commercial import ProductTypeRevision
from catalog.models.products import Item, ProductFamily
from tests.attribute_factories import seed_attributes
from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.test_advanced_product_drafts import PERMISSIONS
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_master_reference_policy import policy
from tests.test_product_mode import set_mode

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def prepared(client, factory, tenant, *, kind="GOODS"):
    company, user, auth, family = await setup_product(factory, tenant, kind=kind)
    auth = headers(
        company,
        tenant=tenant,
        user=user,
        permission=[*PERMISSIONS, "attribute_definition.read", "attribute_option.read"],
    )
    base = f"/v1/companies/{company}/advanced-product-creations"
    response = await client.get(base + "/options?kind=" + kind, headers=auth)
    assert response.status_code == 200, response.text
    options = response.json()
    body = {
        "mode_version": options["mode"]["row_version"],
        "policy_generation": options["mode"]["policy_generation"],
        "source_version": options["defaults"]["configuration"]["source_version"],
        "as_of": options["today"],
        "group_id": options["default_group_id"],
        "profile": {key: value for key, value in family.items() if key != "default_item"},
        "skus": [{"item": family["default_item"], "attributes": []}],
    }
    return company, user, auth, base, body


async def test_one_sku_definition_replay_receipt_and_scope(client, factory, tenant_a, tenant_b):
    company, user, auth, base, body = await prepared(client, factory, tenant_a)
    assert (await client.post(base + "/definitions", json=body)).status_code == 401
    no_create = headers(company, tenant=tenant_a, user=user, permission="item.read")
    denied = await client.post(
        base + "/definitions",
        headers={**no_create, "Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert denied.status_code == 403
    key = str(uuid7())
    result = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": key}, json=body
    )
    assert result.status_code == 201, result.text
    data = result.json()
    assert data["creation"]["status"] == "DEFINED"
    assert data["creation"]["step"] == "SETUP"
    assert data["creation"]["family_id"] == data["family"]["id"]
    assert data["creation"]["sku_ids"] == [data["skus"][0]["id"]]
    creation_id = data["creation"]["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            row = await db.get(AdvancedProductCreation, uuid.UUID(creation_id))
            assert row is not None and row.request["profile"]["code"] == "PRODUCT"
            assert len(row.request_hash) == 64 and row.command_key == key
            events = list(await db.scalars(select(Outbox).where(Outbox.aggregate_id == row.id)))
            assert [event.event_type for event in events] == [
                "catalog.advanced_product_creation.create"
            ]
            assert "PRODUCT" not in str(events[0].payload)
    replay = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": key}, json=body
    )
    assert replay.status_code == 201, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["creation"]["id"] == creation_id
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(func.count(AdvancedProductCreation.id)).where(
                        AdvancedProductCreation.company_id == company
                    )
                )
                == 1
            )
            assert (
                await db.scalar(
                    select(func.count(ProductFamily.id)).where(ProductFamily.company_id == company)
                )
                == 1
            )
    changed = {**body, "profile": {**body["profile"], "name": "Other"}}
    assert (
        await client.post(
            base + "/definitions", headers={**auth, "Idempotency-Key": key}, json=changed
        )
    ).status_code == 422
    status = await client.get(base + "/definitions/" + creation_id, headers=auth)
    assert status.status_code == 200 and status.json()["sku_ids"] == data["creation"]["sku_ids"]
    assert (await client.get(base + "/definitions/" + creation_id)).status_code == 401
    other_company, _, other_auth, _ = await setup_product(factory, tenant_a)
    assert other_company != company
    wrong_company = await client.get(base + "/definitions/" + creation_id, headers=other_auth)
    assert wrong_company.status_code == 403
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert await db.scalar(select(AdvancedProductCreation.id)) is None
    other_user = uuid7()
    await setup_source(
        factory,
        tenant_a,
        company,
        user,
        version=3,
        facts=(
            *all_facts(company, user),
            SnapshotRecord(kind="user", id=other_user, data={"status": "active"}),
        ),
    )
    other_auth = headers(
        company,
        tenant=tenant_a,
        user=other_user,
        permission=[*PERMISSIONS, "attribute_definition.read", "attribute_option.read"],
    )
    # A different actor cannot use the submitter's receipt even with a valid scope.
    other_actor = await client.get(base + "/definitions/" + creation_id, headers=other_auth)
    assert other_actor.status_code == 403


async def test_options_expose_pinned_required_attributes(client, factory, tenant_a):
    company, user, _, base, body = await prepared(client, factory, tenant_a)
    records = await seed_attributes(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(body["profile"]["product_type_revision_id"])
            )
            assert revision is not None
            revision.attribute_set_revision_id = records["attribute_set_revision"]
    auth = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[*PERMISSIONS, "attribute_set.read", "attribute_definition.read"],
    )
    response = await client.get(
        base + "/options?product_type_revision_id=" + body["profile"]["product_type_revision_id"],
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert response.json()["attribute_members"] == [
        {
            "definition_id": str(records["attribute_definition"]),
            "name": "Colour",
            "value_type": "TEXT",
            "measurement_dimension": None,
            "position": 0,
            "is_required": True,
            "allow_variant_axis": True,
            "is_variant_capable": True,
        }
    ]


async def test_options_accept_published_type_shared_by_goods_and_services(
    client, factory, tenant_a
):
    company, _, auth, base, body = await prepared(client, factory, tenant_a)
    revision_id = uuid.UUID(body["profile"]["product_type_revision_id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, revision_id)
            assert revision is not None
            revision.kind = "BOTH"
            revision.inventory_modes = [*revision.inventory_modes, "NON_STOCK"]
            revision.tracking_modes = [*revision.tracking_modes, "NONE"]
    response = await client.get(
        base + "/options?kind=GOODS&product_type_revision_id=" + str(revision_id),
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert response.json()["selected_type"]["kind"] == "BOTH"


async def test_variant_definitions_and_duplicate_rollback(client, factory, tenant_a):
    company, _, auth, base, body = await prepared(client, factory, tenant_a)
    records = await seed_attributes(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
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
            red_id = red.id
    definition = str(records["attribute_definition"])
    blue = str(records["attribute_option"])
    body["attributes"] = [
        {
            "definition_id": definition,
            "is_axis": True,
            "is_required": True,
            "position": 0,
            "options": [blue, str(red_id)],
        }
    ]
    body["skus"][0]["attributes"] = [
        {"definition_id": definition, "option_id": blue, "value_type": "TEXT"}
    ]
    body["skus"].append(
        {
            "item": {
                "sku": "RED-SKU",
                "name": "Red product",
                "base_unit_id": body["skus"][0]["item"]["base_unit_id"],
            },
            "attributes": [
                {"definition_id": definition, "option_id": str(red_id), "value_type": "TEXT"}
            ],
        }
    )
    result = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert result.status_code == 201, result.text
    assert len(result.json()["skus"]) == 2
    assert result.json()["family"]["structure_mode"] == "VARIANT"
    body["profile"]["code"] = "DUPLICATE"
    body["skus"][0]["item"]["sku"] = "BLUE2"
    body["skus"][1]["item"]["sku"] = "BLUE3"
    body["skus"][1]["attributes"] = body["skus"][0]["attributes"]
    rejected = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert rejected.status_code == 409, rejected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(ProductFamily.id).where(
                        ProductFamily.company_id == company, ProductFamily.code == "DUPLICATE"
                    )
                )
                is None
            )
            assert await db.scalar(select(Item.id).where(Item.sku == "BLUE2")) is None
            assert (
                await db.scalar(
                    select(func.count(AdvancedProductCreation.id)).where(
                        AdvancedProductCreation.company_id == company
                    )
                )
                == 1
            )
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "catalog.advanced_product_creation.create"
                    )
                )
                == 1
            )
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "catalog.product_family.create"
                    )
                )
                == 1
            )


async def test_definition_validation_and_field_denial(client, factory, tenant_a):
    company, user, auth, base, body = await prepared(client, factory, tenant_a)
    body["skus"].append({"item": {**body["skus"][0]["item"], "sku": "SKU2"}})
    assert (
        await client.post(
            base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
        )
    ).status_code == 422
    body["skus"][1]["item"]["sku"] = body["skus"][0]["item"]["sku"]
    assert (
        await client.post(
            base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
        )
    ).status_code == 422
    body["skus"] = body["skus"][:1]
    body["profile"]["custom_fields"] = {"unsafe_amount": 1.25}
    assert (
        await client.post(
            base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
        )
    ).status_code == 422
    body["profile"].pop("custom_fields")
    await policy(factory, tenant_a, company, user, "catalog.product_family", "name", "write")
    options = await client.get(base + "/options", headers=auth)
    assert options.status_code == 200, options.text
    body["policy_generation"] = options.json()["mode"]["policy_generation"]
    body["source_version"] = options.json()["defaults"]["configuration"]["source_version"]
    response = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert response.status_code == 403, response.text


async def test_type_forbids_axes_and_rejects_all_rows(client, factory, tenant_a):
    company, _, auth, base, body = await prepared(client, factory, tenant_a)
    records = await seed_attributes(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(body["profile"]["product_type_revision_id"])
            )
            assert revision is not None
            revision.allow_variants = False
    options = await client.get(base + "/options", headers=auth)
    assert options.status_code == 200, options.text
    body["source_version"] = options.json()["defaults"]["configuration"]["source_version"]
    definition = str(records["attribute_definition"])
    body["attributes"] = [
        {
            "definition_id": definition,
            "is_axis": True,
            "is_required": True,
            "position": 0,
            "options": [str(records["attribute_option"])],
        }
    ]
    body["skus"][0]["attributes"] = [
        {
            "definition_id": definition,
            "option_id": str(records["attribute_option"]),
            "value_type": "TEXT",
        }
    ]
    response = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert response.status_code == 422, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(select(ProductFamily.id).where(ProductFamily.company_id == company))
                is None
            )


async def test_mode_change_blocks_definition(client, factory, tenant_a):
    company, user, auth, base, body = await prepared(client, factory, tenant_a)
    manager = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[*PERMISSIONS, "product_configuration.manage"],
    )
    changed, _, _ = await set_mode(client, company, manager, False)
    assert changed.status_code == 200, changed.text
    response = await client.post(
        base + "/definitions", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(select(ProductFamily.id).where(ProductFamily.company_id == company))
                is None
            )
