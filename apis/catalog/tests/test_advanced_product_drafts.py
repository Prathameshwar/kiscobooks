"""Advanced options and private draft contract; no product mutation occurs."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select

from catalog.models.advanced_product_draft import AdvancedProductDraft
from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_master_reference_policy import policy
from tests.test_product_mode import set_mode

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
PERMISSIONS = [
    "item.create",
    "item.read",
    "item.update",
    "unit.read",
    "product_type.read",
    "brand.read",
    "brand_series.read",
    "product_configuration.read",
    "product_definition.read",
    "item_group.read",
    "category_scheme.read",
    "price_plan.read",
]


def draft_body(options: dict, *, name: str = "Widget") -> dict:
    return {
        "mode_version": options["mode"]["row_version"],
        "policy_generation": options["mode"]["policy_generation"],
        "source_version": options["defaults"]["configuration"]["source_version"],
        "family_field_version": options["family_fields"]["source_version"],
        "sku_field_version": options["sku_fields"]["source_version"],
        "step": 1,
        "content": {"profile": {"kind": "GOODS", "name": name}, "skus": []},
    }


async def prepared(client, factory, tenant):
    company, user, _, _ = await setup_product(factory, tenant)
    auth = headers(
        company,
        tenant=tenant,
        user=user,
        permission=PERMISSIONS,
    )
    base = f"/v1/companies/{company}/advanced-product-creations"
    result = await client.get(base + "/options", headers=auth)
    assert result.status_code == 200, result.text
    assert result.json()["mode"]["product_family_sku_enabled"] is True
    assert result.json()["family_fields"]["entity_type"] == "catalog.product_family"
    return company, user, auth, base, result.json()


async def test_options_mode_scope_and_strict_query(client, factory, tenant_a):
    company, user, auth, base, data = await prepared(client, factory, tenant_a)
    assert data["company_id"] == str(company)
    assert data["max_skus_per_draft"] == 64
    assert data["price_levels_accessible"] is True
    assert (await client.get(base + "/options?unknown=1", headers=auth)).status_code == 422
    assert (
        await client.get(base + "/options?kind=GOODS&kind=SERVICE", headers=auth)
    ).status_code == 422
    assert (await client.get(base + "/options")).status_code == 401
    missing_create = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission="product_configuration.read",
    )
    assert (await client.get(base + "/options", headers=missing_create)).status_code == 403
    no_price = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[key for key in PERMISSIONS if key != "price_plan.read"],
    )
    price_result = await client.get(base + "/options", headers=no_price)
    if data["defaults"]["configuration"]["pricing"]["sale_price_mode"] == "REQUIRED":
        assert price_result.status_code == 403
    else:
        assert price_result.status_code == 200, price_result.text
        assert price_result.json()["price_levels_accessible"] is False
    simple_company, _, simple_auth, _ = await setup_product(factory, tenant_a, advanced=False)
    simple = await client.get(
        f"/v1/companies/{simple_company}/advanced-product-creations/options",
        headers=simple_auth,
    )
    assert simple.status_code == 409


async def test_save_replay_replace_delete_and_tenant_isolation(client, factory, tenant_a, tenant_b):
    company, user, auth, base, options = await prepared(client, factory, tenant_a)
    body = draft_body(options)
    key = str(uuid7())
    created = await client.post(
        base + "/drafts", headers={**auth, "Idempotency-Key": key}, json=body
    )
    assert created.status_code == 201, created.text
    draft_id = created.json()["id"]
    assert created.json()["row_version"] == 1
    assert created.json()["needs_review"] is False
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = list(
                await db.scalars(select(Outbox).where(Outbox.aggregate_id == uuid.UUID(draft_id)))
            )
            assert len(events) == 1
            assert events[0].event_type == "catalog.advanced_product_draft.create"
            assert "Widget" not in str(events[0].payload)
    again = await client.post(base + "/drafts", headers={**auth, "Idempotency-Key": key}, json=body)
    assert again.status_code == 200, again.text
    assert again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["id"] == draft_id
    assert (
        await client.post(
            base + "/drafts",
            headers={**auth, "Idempotency-Key": key},
            json=draft_body(options, name="Different"),
        )
    ).status_code == 409
    listed = await client.get(base + "/drafts", headers=auth)
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert "content" not in listed.json()[0]
    changed = {**draft_body(options, name="Revised"), "expected_version": 1, "step": 2}
    saved = await client.put(base + "/drafts/" + draft_id, headers=auth, json=changed)
    assert saved.status_code == 200, saved.text
    assert saved.json()["row_version"] == 2 and saved.json()["step"] == 2
    assert (
        await client.put(base + "/drafts/" + draft_id, headers=auth, json=changed)
    ).status_code == 409
    other_user = uuid7()
    await setup_source(
        factory,
        tenant_a,
        company,
        user,
        version=3,
        facts=(
            *all_facts(company, user),
            SnapshotRecord(
                kind="user",
                id=other_user,
                data={"status": "active"},
            ),
        ),
    )
    other_actor = headers(company, tenant=tenant_a, user=other_user, permission=PERMISSIONS)
    assert (await client.get(base + "/drafts/" + draft_id, headers=other_actor)).status_code == 404
    other_list = await client.get(base + "/drafts", headers=other_actor)
    assert other_list.status_code == 200 and other_list.json() == []
    after_source = await client.get(base + "/drafts/" + draft_id, headers=auth)
    assert after_source.status_code == 200 and after_source.json()["needs_review"] is True
    stale_source = {**draft_body(options), "expected_version": 2}
    assert (
        await client.put(base + "/drafts/" + draft_id, headers=auth, json=stale_source)
    ).status_code == 409
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert await db.scalar(select(AdvancedProductDraft.id)) is None
    other_company, _, other_auth, _ = await setup_product(factory, tenant_a)
    assert other_company != company
    assert (await client.get(base + "/drafts/" + draft_id, headers=other_auth)).status_code == 403
    deleted = await client.delete(base + "/drafts/" + draft_id, headers={**auth, "If-Match": "2"})
    assert deleted.status_code == 204, deleted.text
    assert (await client.get(base + "/drafts/" + draft_id, headers=auth)).status_code == 404
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = list(
                await db.scalars(select(Outbox).where(Outbox.aggregate_id == uuid.UUID(draft_id)))
            )
            assert {row.event_type for row in events} == {
                "catalog.advanced_product_draft.create",
                "catalog.advanced_product_draft.update",
                "catalog.advanced_product_draft.delete",
            }
            assert all("Widget" not in str(row.payload) for row in events)


async def test_field_denial_source_review_and_bounds(client, factory, tenant_a):
    company, user, auth, base, options = await prepared(client, factory, tenant_a)
    body = draft_body(options)
    created = await client.post(
        base + "/drafts", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert created.status_code == 201, created.text
    draft_id = created.json()["id"]
    assert (
        await client.post(
            base + "/drafts",
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={
                **body,
                "content": {"profile": {"name": "Widget", "kind": "GOODS", "cost": 1.25}},
            },
        )
    ).status_code == 422
    await policy(factory, tenant_a, company, user, "catalog.product_family", "name", "write")
    refreshed = await client.get(base + "/options", headers=auth)
    assert refreshed.status_code == 200, refreshed.text
    stale = await client.get(base + "/drafts/" + draft_id, headers=auth)
    assert stale.status_code == 200 and stale.json()["needs_review"] is True
    changed = {**draft_body(refreshed.json()), "expected_version": 1}
    assert (
        await client.put(base + "/drafts/" + draft_id, headers=auth, json=changed)
    ).status_code == 403
    await policy(
        factory, tenant_a, company, user, "catalog.product_family", "name", "read", version=4
    )
    assert (await client.get(base + "/drafts/" + draft_id, headers=auth)).status_code == 403


async def test_mode_change_preserves_private_draft_and_blocks_new_save(client, factory, tenant_a):
    company, user, auth, base, options = await prepared(client, factory, tenant_a)
    body = draft_body(options)
    created = await client.post(
        base + "/drafts", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert created.status_code == 201, created.text
    manager = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[*PERMISSIONS, "product_configuration.manage"],
    )
    changed, _, _ = await set_mode(client, company, manager, False)
    assert changed.status_code == 200, changed.text
    retained = await client.get(base + "/drafts/" + created.json()["id"], headers=auth)
    assert retained.status_code == 200 and retained.json()["needs_review"] is True
    blocked = await client.post(
        base + "/drafts", headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert blocked.status_code == 409
