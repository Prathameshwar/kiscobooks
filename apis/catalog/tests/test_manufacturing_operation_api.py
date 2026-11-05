"""Operation definitions are scoped, revisioned and never execute production."""

import json
import uuid
from pathlib import Path

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, ManufacturingOperationRevision, Outbox
from catalog.models.products import Item, ProductFamily
from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers


async def test_operation_field_denials_roll_back_commands_and_hide_status_filters(
    client, factory, tenant_a
):
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    await setup_source(factory, tenant_a, company, user, facts=facts)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "manufacturing_operation.read",
            "manufacturing_operation.manage",
            "manufacturing_operation.publish",
        ],
    )
    root = f"/v1/companies/{company}/manufacturing-operations"
    master = await client.post(
        root, headers=command_headers(current), json={"code": "CUT", "name": "Cutting"}
    )
    revisions = root + "/" + master.json()["id"] + "/revisions"
    base = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **base.data,
            "entity_type": "catalog.manufacturing_operation_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "specification",
            "access": "write",
            "condition": None,
        },
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    payload = {"specification": "Approved cut", "change_reason": "Initial definition"}
    receipt = command_headers(current)
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ManufacturingOperationRevision.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1
    await setup_source(factory, tenant_a, company, user, version=4, facts=facts)
    created = await client.post(revisions, headers=receipt, json=payload)
    assert created.status_code == 201, created.text
    assert (await client.post(revisions, headers=receipt, json=payload)).json() == created.json()
    deny_status = deny.model_copy(update={"data": {**deny.data, "field_key": "status"}})
    await setup_source(factory, tenant_a, company, user, version=5, facts=(*facts, deny_status))
    detail = revisions + "/" + created.json()["id"]
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 403
    hidden = deny.model_copy(
        update={"data": {**deny.data, "field_key": "status", "access": "read"}}
    )
    await setup_source(factory, tenant_a, company, user, version=6, facts=(*facts, hidden))
    assert "status" not in (await client.get(detail, headers=current)).json()
    assert (await client.get(revisions + "?status=DRAFT", headers=current)).status_code == 403


async def test_operation_service_choices_require_active_service_and_item_read(
    client, factory, tenant_a
):
    company, user, product_actor, body = await setup_product(factory, tenant_a, kind="SERVICE")
    product = await client.post(
        f"/v1/companies/{company}/product-families",
        headers=command_headers(product_actor),
        json=body,
    )
    assert product.status_code == 201, product.text
    item_id = uuid.UUID(product.json()["default_item"]["id"])
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["manufacturing_operation.read", "manufacturing_operation.manage", "item.read"],
    )
    root = f"/v1/companies/{company}/manufacturing-operations"
    assert (await client.get(root + "/service-options", headers=current)).json()["items"] == []
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, item_id)
            family = await db.get(ProductFamily, item.family_id)
            item.status = family.status = "ACTIVE"
    options = await client.get(root + "/service-options", headers=current)
    assert options.status_code == 200, options.text
    assert [row["id"] for row in options.json()["items"]] == [str(item_id)]
    assert options.json()["items"][0]["status"] == "ACTIVE"
    reader = headers(
        company, tenant=tenant_a, user=user, permission=["manufacturing_operation.read"]
    )
    assert (await client.get(root + "/service-options", headers=reader)).status_code == 403
    assert (
        await client.get(root + "/service-options?kind=GOODS", headers=current)
    ).status_code == 422


async def test_operation_metadata_contract(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "manufacturing_operation.read",
            "manufacturing_operation.manage",
            "manufacturing_operation.publish",
        ],
    )
    captured = {}
    for entity in ["manufacturing_operation", "manufacturing_operation_revision"]:
        for operation in [
            "read",
            "create",
            "update",
            *(["publish"] if entity.endswith("_revision") else []),
        ]:
            result = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert result.status_code == 200, result.text
            captured[entity + ":" + operation] = result.json()["fields"]
    fields = {row["key"]: row for row in captured["manufacturing_operation_revision:create"]}
    assert fields["specification"]["control"]["max_length"] == 2000
    assert fields["change_reason"]["control"]["max_length"] == 500
    assert fields["service_item_id"]["control"]["kind"] == "reference"
    assert not fields["status"]["writable"]
    published = {row["key"]: row for row in captured["manufacturing_operation_revision:publish"]}
    assert published["status"]["writable"] and published["published_at"]["writable"]
    destination = (
        Path(__file__).resolve().parents[3] / ".tools/extension-masters/operation-fields.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(captured, indent=2), encoding="utf-8")


async def test_operation_access_scope_validation_and_versions(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    permissions = [
        "manufacturing_operation.read",
        "manufacturing_operation.manage",
        "manufacturing_operation.publish",
    ]
    current = headers(company, tenant=tenant_a, user=user, permission=permissions)
    reader = headers(company, tenant=tenant_a, user=user, permission=permissions[:1])
    root = f"/v1/companies/{company}/manufacturing-operations"
    assert (await client.get(root)).status_code == 401
    assert (
        await client.post(
            root, headers=command_headers(reader), json={"code": "CUT", "name": "Cutting"}
        )
    ).status_code == 403
    created = await client.post(
        root, headers=command_headers(current), json={"code": "CUT", "name": "Cutting"}
    )
    assert created.status_code == 201, created.text
    master = root + "/" + created.json()["id"]
    assert (await client.get(master, headers=reader)).status_code == 200
    assert (
        await client.patch(
            master, headers=command_headers(current), json={"expected_version": 9, "name": "Other"}
        )
    ).status_code == 409
    assert (
        await client.post(
            master + "/revisions",
            headers=command_headers(current),
            json={"specification": "  ", "change_reason": "Initial"},
        )
    ).status_code == 422
    draft = await client.post(
        master + "/revisions",
        headers=command_headers(current),
        json={"specification": "Approved cut", "change_reason": "Initial"},
    )
    revision = master + "/revisions/" + draft.json()["id"]
    assert (
        await client.post(
            revision + "/retire", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    assert (
        await client.post(
            revision + "/publish", headers=command_headers(reader), json={"expected_version": 1}
        )
    ).status_code == 403
    other = await client.post(
        root, headers=command_headers(current), json={"code": "PACK", "name": "Packing"}
    )
    wrong_parent = revision.replace(created.json()["id"], other.json()["id"])
    assert (await client.get(wrong_parent, headers=current)).status_code == 403
    await setup_source(factory, tenant_b, company, user)
    alien = headers(company, tenant=tenant_b, user=user, permission=permissions)
    assert (await client.get(master, headers=alien)).status_code == 404
    assert (await client.get(revision, headers=alien)).status_code == 404


async def test_operation_definition_workflow(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "manufacturing_operation.read",
            "manufacturing_operation.manage",
            "manufacturing_operation.publish",
        ],
    )
    root = f"/v1/companies/{company}/manufacturing-operations"
    created = await client.post(
        root,
        headers=command_headers(current),
        json={
            "code": "CUT",
            "name": "Cutting",
        },
    )
    assert created.status_code == 201, created.text
    master = root + "/" + created.json()["id"]
    payload = {
        "specification": "Cut to the approved component dimensions.",
        "change_reason": "Initial definition",
    }
    receipt = command_headers(current)
    draft = await client.post(master + "/revisions", headers=receipt, json=payload)
    assert draft.status_code == 201, draft.text
    assert draft.json()["status"] == "DRAFT"
    replay = await client.post(master + "/revisions", headers=receipt, json=payload)
    assert replay.headers["Idempotency-Replayed"] == "true"
    revision = master + "/revisions/" + draft.json()["id"]
    published = await client.post(
        revision + "/publish", headers=command_headers(current), json={"expected_version": 1}
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert (
        await client.patch(
            revision,
            headers=command_headers(current),
            json={"expected_version": 2, "specification": "Changed"},
        )
    ).status_code == 409
    retired = await client.post(
        revision + "/retire", headers=command_headers(current), json={"expected_version": 2}
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "RETIRED"
    assert (await client.get(revision, headers=current)).json()["specification"] == payload[
        "specification"
    ]
    assert (await client.get(root, headers=current)).json()["items"][0]["name"] == "Cutting"
