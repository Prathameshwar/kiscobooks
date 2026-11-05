"""Regression coverage for product dependencies and aggregate validation."""

import datetime as dt
import uuid
from typing import Any, cast

import pytest
from billing_platform.db import tenant_scope
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
    ProductFamily,
    ProductTypeRevision,
)
from catalog.models.projections import CompanyFeatureProjection
from catalog.models.tax import ItemInventoryProfile
from catalog.tasks import activation
from tests.attribute_factories import seed_attributes
from tests.configuration_factories import publish_configuration
from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.product_integrity_factories import features
from tests.profile_factories import seed_identifier_profile
from tests.tax_factories import seed_tax
from tests.test_commercial_api import command_headers
from tests.test_pricing_levels_units import feature
from tests.test_pricing_resolution import query
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def put(
    client: AsyncClient, path: str, auth: dict[str, str], body: dict[str, Any], status: int = 200
) -> dict[str, Any]:
    response = await client.put(path, headers=command_headers(auth), json=body)
    assert response.status_code == status, response.text
    return cast(dict[str, Any], response.json())


async def post_ok(
    client: AsyncClient, path: str, auth: dict[str, str], body: dict[str, Any], status: int = 200
) -> dict[str, Any]:
    response = await client.post(path, headers=command_headers(auth), json=body)
    assert response.status_code == status, response.text
    return cast(dict[str, Any], response.json())


async def test_scalar_bypasses_permitted_options(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    root = f"/v1/companies/{company}"
    definition = str(ids["attribute_definition"])
    await put(
        client,
        root + f"/product-families/{product['family']['id']}/attributes",
        auth,
        {
            "expected_version": 1,
            "attributes": [
                {
                    "definition_id": definition,
                    "position": 0,
                    "options": [str(ids["attribute_option"])],
                    "is_required": True,
                }
            ],
        },
    )
    path = root + f"/items/{product['default_item']['id']}/attributes"
    selection = {"definition_id": definition, "value_type": "TEXT"}
    await put(
        client,
        path,
        auth,
        {
            "expected_version": 1,
            "attributes": [{**selection, "value_text": "Not an allowed colour"}],
        },
        status=422,
    )
    assert (await client.get(path, headers=auth)).json()["items"] == []
    accepted = await put(
        client,
        path,
        auth,
        {
            "expected_version": 1,
            "attributes": [{**selection, "option_id": str(ids["attribute_option"])}],
        },
    )
    assert accepted["item_version"] == 2


async def test_family_save_overwrites_newer_sku_edit(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    root = f"/v1/companies/{company}"
    definition = str(ids["attribute_definition"])
    family = root + f"/product-families/{product['family']['id']}/attributes"
    item = root + f"/items/{product['default_item']['id']}/attributes"
    declaration = {"definition_id": definition, "position": 0}
    old = {"definition_id": definition, "value_type": "TEXT", "value_text": "Old"}
    body = {"expected_version": 1, "attributes": [declaration], "default_item_attributes": [old]}
    await put(client, family, auth, body, status=422)
    saved = await put(client, family, auth, {**body, "expected_default_item_version": 1})
    assert saved["item_version"] == 2
    edited = await put(
        client,
        item,
        auth,
        {"expected_version": 2, "attributes": [{**old, "value_text": "New user edit"}]},
    )
    stale = {
        **body,
        "expected_version": saved["family_version"],
        "expected_default_item_version": 2,
    }
    await put(client, family, auth, stale, status=409)
    stored = (await client.get(item, headers=auth)).json()
    detail = await client.get(item + "/" + stored["items"][0]["id"], headers=auth)
    assert detail.status_code == 200, detail.text
    assert detail.json()["value_text"] == "New user edit"
    corrected = await put(
        client, family, auth, {**stale, "expected_default_item_version": edited["item_version"]}
    )
    assert corrected["item_version"] == 4
    assert corrected["family_version"] == 3


async def test_referenced_price_level_retirement(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    await feature(factory, tenant_a, uuid.UUID(root.rsplit("/", 1)[1]), ids["actor_user"])
    setup = await foundation(client, root, auth, ids)
    levels = (await client.get(root + "/price-levels", headers=auth)).json()["items"]
    second = (
        next(x for x in levels if x["ordinal"] == 2)
        if "ordinal" in levels[0]
        else next(x for x in levels if x["code"] == "PRICE2")
    )
    plan = await create(
        client,
        root,
        auth,
        "/price-plans",
        {
            "code": "SECOND",
            "name": "Second",
            "purpose": "SALE",
            "price_level_id": second["id"],
            "currency": "INR",
            "tax_basis": "EXCLUSIVE",
        },
    )
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": plan["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    _, price = await publish_price(client, root, auth, {**setup, "series": series}, amount="80")
    await create(
        client,
        root,
        auth,
        "/company-pricing-policies",
        {
            **guard(price),
            "default_level_id": second["id"],
            "valid_from": "2091-01-01",
            "supersedes_id": setup["policy"]["id"],
            "expected_previous_version": 1,
        },
    )
    before = await client.post(
        root + "/prices/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
    )
    assert before.status_code == 200, before.text
    retired = await client.patch(
        root + "/price-levels/" + second["id"],
        headers=command_headers(auth),
        json={"expected_version": 1, "name": "Second", "is_active": False},
    )
    assert retired.status_code == 409, retired.text
    after = await client.post(
        root + "/prices/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
    )
    assert after.status_code == 200 and after.json() == before.json(), after.text


async def test_future_unit_grid_conflict(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    # Exercise grid compatibility; a barcode would reject any meaning change first.
    root, auth, ids = await setup_pricing(factory, tenant_a, with_barcode=False)
    item_path = root + f"/items/{ids['item']}"
    item = (await client.get(item_path, headers=auth)).json()
    alternate = await post_ok(
        client,
        item_path + "/unit-bindings",
        auth,
        {
            "expected_version": 1,
            "code": "FUTURE",
            "unit_id": item["base_unit_id"],
            "role": "SALE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "valid_from": "2092-01-01",
        },
    )
    bindings = (await client.get(item_path + "/unit-bindings", headers=auth)).json()["items"]
    future = next(x for x in bindings if x["code"] == "FUTURE")
    future_revision = (
        await client.get(root + f"/item-unit-bindings/{future['id']}/revisions", headers=auth)
    ).json()["items"][0]
    base = next(x for x in bindings if x["code"] == "BASE")
    await post_ok(
        client,
        item_path + "/unit-revisions",
        auth,
        {
            "expected_version": alternate["item_version"],
            "binding_id": base["id"],
            "code": "BASE",
            "unit_id": item["base_unit_id"],
            "role": "BASE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "2",
            "valid_from": "2091-01-01",
        },
        status=422,
    )
    response = await client.post(
        item_path + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2092-01-01",
            "components": [{"unit_revision_id": future_revision["id"], "quantity": "1"}],
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("missing", ["batch_tracking", "serial_tracking", "expiry_tracking"])
async def test_tracking_activation_without_company_capabilities(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    identifier = await seed_identifier_profile(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            revision.tracking_modes = ["BATCH_SERIAL"]
            template = await db.get(
                InventoryProfileTemplateRevision, ids["inventory_profile_template_revision"]
            )
            assert template is not None
            template.lot_tracking = template.serial_tracking = template.expiry_required = True
            template.identifier_profile_id = identifier
            flags = list(
                await db.scalars(
                    select(CompanyFeatureProjection.feature_key).where(
                        CompanyFeatureProjection.is_enabled.is_(True)
                    )
                )
            )
    assert not {"batch_tracking", "serial_tracking", "expiry_tracking"}.intersection(flags)
    capabilities = {"batch_tracking", "serial_tracking", "expiry_tracking"}
    await features(factory, tenant_a, company, ids["actor_user"], capabilities - {missing})
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    item = root + f"/items/{ids['item']}"
    preview = await client.post(
        item + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 409 and missing in preview.text, preview.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(ItemInventoryProfile).where(ItemInventoryProfile.item_id == ids["item"])
                )
                is None
            )

    draft = await client.post(
        root + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": str(ids["product_configuration_scope"]),
            "effective_from": "2091-01-01",
            "change_reason": "Tracking selection",
            "profiles": {
                "inventory_template_revision_mode": "VALUE",
                "inventory_template_revision_id": str(ids["inventory_profile_template_revision"]),
            },
        },
    )
    assert draft.status_code == 409 and missing in draft.text, draft.text
    await features(factory, tenant_a, company, ids["actor_user"], capabilities, version=4)
    preview = await client.post(
        item + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    await post_ok(
        client,
        item + "/activate",
        auth,
        {
            key: preview.json()[key]
            for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
        },
    )
    facts = await client.get(
        item + "/effective-facts", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert facts.status_code == 200, facts.text
    assert facts.json()["inventory"]["identifier_profile_id"] == str(identifier)
    assert facts.json()["stock_execution"]["state"] == "UNAVAILABLE"
    with tenant_scope(tenant_a):
        async with factory() as db:
            profile = await db.scalar(
                select(ItemInventoryProfile).where(ItemInventoryProfile.item_id == ids["item"])
            )
            assert profile is not None
            assert profile.lot_tracking and profile.serial_tracking and profile.expiry_required
            assert profile.identifier_profile_id == identifier
        async with factory.begin() as db:
            # Simulate a retired template while the activated item still pins its profile.
            revision = await db.get(
                InventoryProfileTemplateRevision, ids["inventory_profile_template_revision"]
            )
            assert revision is not None
            template = await db.get(InventoryProfileTemplate, revision.template_id)
            assert template is not None
            template.is_active = False
    retired = await client.post(
        root + f"/identifier-profiles/{identifier}/deactivate",
        headers=command_headers(auth),
        json={"expected_version": 1},
    )
    assert retired.status_code == 409, retired.text


async def test_group_move_breaks_active_adoption(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    parent = await create(
        client,
        root,
        auth,
        "/item-groups",
        {"code": "PARENT", "name": "Parent", "allowed_kind": "GOODS", "valid_from": "2090-01-01"},
    )
    group_path = root + f"/item-groups/{ids['item_group']}"
    await post_ok(
        client,
        group_path + "/reparent",
        auth,
        {
            "expected_version": 1,
            "expected_generation": parent["policy_generation"],
            "parent_group_id": parent["id"],
            "effective_from": "2090-01-02",
        },
    )
    await publish_configuration(
        client,
        root,
        auth,
        scope={"scope_kind": "GROUP", "group_id": parent["id"]},
        options={"brand_mode": "DISABLED"},
    )
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 2, 12, tzinfo=dt.UTC))
    item = root + f"/items/{ids['item']}"
    preview = await client.post(
        item + "/activation-preview", headers=auth, json={"as_of": "2090-01-02"}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    await post_ok(
        client,
        item + "/activate",
        auth,
        {
            k: preview.json()[k]
            for k in ("as_of", "expected_version", "expected_family_version", "preview_token")
        },
    )
    current = (await client.get(group_path, headers=auth)).json()
    await post_ok(
        client,
        group_path + "/reparent",
        auth,
        {
            "expected_version": current["row_version"],
            "expected_generation": current["policy_generation"],
            "parent_group_id": None,
            "effective_from": "2091-01-01",
        },
        status=409,
    )
    after = await client.get(item + "/requirements", headers=auth, params={"as_of": "2091-01-01"})
    assert after.status_code == 200, after.text
    assert (await client.get(group_path, headers=auth)).json() == current


async def test_minimum_patch_ignores_sku_grid(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    # Keep the base grid revisable so the PATCH reaches its minimum-quantity check.
    root, auth, ids = await setup_pricing(factory, tenant_a, with_barcode=False)
    item = root + f"/items/{ids['item']}"
    current = (await client.get(item, headers=auth)).json()
    revised = await client.post(
        item + "/unit-revisions",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "binding_id": str(ids["item_unit_binding"]),
            "code": "BASE",
            "unit_id": current["base_unit_id"],
            "role": "BASE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "2",
            "valid_from": "2091-01-01",
        },
    )
    assert revised.status_code == 200, revised.text
    patched = await client.patch(
        item,
        headers=command_headers(auth),
        json={"expected_version": revised.json()["item_version"], "min_sale_quantity": "3"},
    )
    assert patched.status_code == 422, patched.text
    unchanged = (await client.get(item, headers=auth)).json()
    assert unchanged["min_sale_quantity"] == current["min_sale_quantity"]
    accepted = await client.patch(
        item,
        headers=command_headers(auth),
        json={"expected_version": revised.json()["item_version"], "min_sale_quantity": "4"},
    )
    assert accepted.status_code == 200, accepted.text


async def test_alternate_binding_mistaken_for_compound_entry(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    root = f"/v1/companies/{company}"
    item = root + f"/items/{product['default_item']['id']}"
    await publish_configuration(client, root, auth, options={"compound_units_mode": "DISABLED"})
    body = {
        "expected_version": 1,
        "code": "BASE",
        "unit_id": product["default_item"]["base_unit_id"],
        "role": "BASE",
        "numerator": 1,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "1",
        "valid_from": "2090-01-01",
    }
    base = await client.post(item + "/unit-bindings", headers=command_headers(auth), json=body)
    assert base.status_code == 200, base.text
    alternate = await client.post(
        item + "/unit-bindings",
        headers=command_headers(auth),
        json={
            **body,
            "expected_version": base.json()["item_version"],
            "code": "PACK",
            "role": "PACK",
        },
    )
    assert alternate.status_code == 200, alternate.text
    bindings = (await client.get(item + "/unit-bindings", headers=auth)).json()["items"]
    pack = next(x for x in bindings if x["code"] == "PACK")
    revision = (
        await client.get(root + f"/item-unit-bindings/{pack['id']}/revisions", headers=auth)
    ).json()["items"][0]
    quantity = await client.post(
        item + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [{"unit_revision_id": revision["id"], "quantity": "1"}],
        },
    )
    assert quantity.status_code == 200, quantity.text
    compound = await client.post(
        item + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [
                {"unit_revision_id": revision["id"], "quantity": "1"},
                {"unit_revision_id": revision["id"], "quantity": "1"},
            ],
        },
    )
    assert compound.status_code == 422 and "compound" in compound.text, compound.text
    requirements = await client.get(
        item + "/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert (
        requirements.status_code == 200
        and "forbidden_compound_units" not in requirements.json()["missing"]
    ), requirements.text
