import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.attributes import AttributeValue
from catalog.models import (
    CatalogDefaultProfile,
    InventoryProfileTemplateRevision,
    ProductFamily,
    ProductTypeRevision,
)
from catalog.models.attributes import AttributeOption
from catalog.models.products import Item
from tests.attribute_factories import seed_attributes
from tests.configuration_factories import publish_configuration, setup_configuration
from tests.inventory_factories import seed_template
from tests.product_definition_factories import seed_definitions
from tests.product_factories import setup_product
from tests.product_integrity_factories import features
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_effective_item_exposes_full_expiry_policy(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    _, template_id = await seed_template(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            template = await db.get(InventoryProfileTemplateRevision, template_id)
            defaults = await db.get(CatalogDefaultProfile, ids["catalog_default_profile"])
            family = await db.get(ProductFamily, ids["product_family"])
            assert template is not None and defaults is not None and family is not None
            type_revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert type_revision is not None
            type_revision.inventory_modes = ["STOCK"]
            type_revision.tracking_modes = ["BATCH"]
            template.published_at = utcnow()
            template.lot_tracking = True
            template.expiry_required = True
            template.manufacture_date_required = True
            template.shelf_life_days = 730
            template.minimum_remaining_life_days = 30
            template.issue_strategy = "FEFO"
            defaults.inventory_template_revision_mode = "VALUE"
            defaults.inventory_template_revision_id = template_id
    await features(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        {"inventory", "batch_tracking", "expiry_tracking"},
    )
    auth = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS),
    )
    response = await client.get(
        f"/v1/companies/{company}/items/{ids['item']}/effective-facts?as_of=2090-01-01",
        headers=auth,
    )
    assert response.status_code == 200, response.text
    inventory = response.json()["inventory"]
    assert inventory["manufacture_date_required"] is True
    assert inventory["shelf_life_days"] == 730
    assert inventory["minimum_remaining_life_days"] == 30


async def create_product(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    service: bool = False,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], dict[str, Any]]:
    if service:
        company, user, _, body = await setup_product(factory, tenant, kind="SERVICE")
        auth = headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS))
    else:
        company, user, auth, body = await setup_configuration(factory, tenant)
    response = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert response.status_code == 201, response.text
    return company, user, auth, response.json()


@pytest.mark.parametrize("service", [False, True])
async def test_effective_item_facts_separate_definition_from_stock_execution(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    service: bool,
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a, service=service)
    item = product["default_item"]["id"]
    path = f"/v1/companies/{company}/items/{item}/effective-facts?as_of=2090-01-01"
    assert (await client.get(path)).status_code == 401
    invalid = await client.get(path.replace("2090-01-01", "not-a-date"), headers=auth)
    assert invalid.status_code == 422
    response = await client.get(path, headers=auth)
    assert response.status_code == 200, response.text
    facts = response.json()
    assert facts["item_id"] == item
    assert facts["product_type_revision_id"] == product["family"]["product_type_revision_id"]
    assert facts["group_id"] is None
    assert facts["units"] == []
    assert facts["configuration"]["company_id"] == str(company)
    assert facts["requirements"]["item_id"] == item
    if service:
        assert facts["kind"] == "SERVICE"
        assert facts["stock_execution"] == {"state": "NOT_APPLICABLE", "reasons": []}
    else:
        assert facts["kind"] == "GOODS"
        assert facts["stock_execution"]["state"] == "UNAVAILABLE"
        assert "accounting_stock_execution_unavailable" in facts["stock_execution"]["reasons"]
    other_company, _, _, other_product = await create_product(
        client, factory, tenant_a, service=service
    )
    other_item = other_product["default_item"]["id"]
    wrong_scope = (
        f"/v1/companies/{other_company}/items/{other_item}/effective-facts?as_of=2090-01-01"
    )
    assert (await client.get(wrong_scope, headers=auth)).status_code == 403


async def test_non_stock_goods_do_not_require_stock_execution(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(body["product_type_revision_id"])
            )
            assert revision is not None
            revision.inventory_modes = ["NON_STOCK"]
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    created = await client.post(
        f"/v1/companies/{company}/product-families",
        headers=command_headers(auth),
        json=body,
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["default_item"]["id"]
    facts = await client.get(
        f"/v1/companies/{company}/items/{item_id}/effective-facts?as_of=2090-01-01",
        headers=auth,
    )
    assert facts.status_code == 200, facts.text
    assert facts.json()["kind"] == "GOODS"
    assert facts.json()["inventory"] is None
    assert facts.json()["stock_execution"] == {"state": "NOT_APPLICABLE", "reasons": []}


async def test_effective_item_facts_refuse_hidden_source_field(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a)
    item = product["default_item"]["id"]
    await policy(factory, tenant_a, company, user, "catalog.item", "min_sale_quantity", "read")
    response = await client.get(
        f"/v1/companies/{company}/items/{item}/effective-facts?as_of=2090-01-01",
        headers=auth,
    )
    assert response.status_code == 403


async def test_effective_item_facts_refuse_conditionally_hidden_group_assignment(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a)
    family = product["family"]["id"]
    item = product["default_item"]["id"]
    base = f"/v1/companies/{company}"
    group = await client.post(
        base + "/item-groups",
        headers=command_headers(auth),
        json={"code": "PRIVATE", "name": "Private", "valid_from": "2090-01-01"},
    )
    assert group.status_code == 201, group.text
    assigned = await client.post(
        base + f"/product-families/{family}/groups",
        headers=command_headers(auth),
        json={"expected_version": 1, "group_id": group.json()["id"], "valid_from": "2090-01-01"},
    )
    assert assigned.status_code == 200, assigned.text
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.family_group_assignment",
        "group_id",
        "read",
        condition={"field": "row_version", "cmp": "gt", "value": 0},
    )
    response = await client.get(
        base + f"/items/{item}/effective-facts?as_of=2090-01-01", headers=auth
    )
    assert response.status_code == 403


async def test_product_assignments_units_barcodes_and_protected_lists(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a)
    base = f"/v1/companies/{company}"
    family = product["family"]["id"]
    item = product["default_item"]["id"]
    group = await client.post(
        base + "/item-groups",
        headers=command_headers(auth),
        json={"code": "GOODS", "name": "Goods", "valid_from": "2090-01-01"},
    )
    assert group.status_code == 201, group.text
    assigned = await client.post(
        base + f"/product-families/{family}/groups",
        headers=command_headers(auth),
        json={"expected_version": 1, "group_id": group.json()["id"], "valid_from": "2090-01-01"},
    )
    assert assigned.status_code == 200, assigned.text
    binding = {
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
    receipt = command_headers(auth)
    created = await client.post(
        base + f"/items/{item}/unit-bindings", headers=receipt, json=binding
    )
    assert created.status_code == 200, created.text
    effective = await client.get(
        base + f"/items/{item}/effective-facts?as_of=2090-01-01", headers=auth
    )
    assert effective.status_code == 200, effective.text
    facts = effective.json()
    assert facts["group_id"] == group.json()["id"]
    assert facts["group_assignment_id"] is not None
    assert len(facts["units"]) == 1
    assert facts["units"][0]["usage_role"] == "BASE"
    assert facts["units"][0]["quantity_increment"] == "1.0000"
    assert (
        await client.post(base + f"/items/{item}/unit-bindings", headers=receipt, json=binding)
    ).headers["Idempotency-Replayed"] == "true"
    bindings = await client.get(base + f"/items/{item}/unit-bindings", headers=auth)
    assert bindings.status_code == 200, bindings.text
    binding_id = bindings.json()["items"][0]["id"]
    barcode = await client.post(
        base + f"/items/{item}/barcodes",
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "binding_id": binding_id,
            "value": "4006381333931",
            "symbology": "GTIN",
        },
    )
    assert barcode.status_code == 200, barcode.text
    invalid = await client.post(
        base + f"/items/{item}/barcodes",
        headers=command_headers(auth),
        json={"expected_version": 3, "value": "4006381333932", "symbology": "GTIN"},
    )
    assert invalid.status_code == 422, invalid.text
    scheme = await client.post(
        base + "/category-schemes",
        headers=command_headers(auth),
        json={"code": "DEPT", "name": "Department", "membership_mode": "SINGLE"},
    )
    assert scheme.status_code == 201, scheme.text
    category = await client.post(
        base + "/item-categories",
        headers=command_headers(auth),
        json={"code": "APPAREL", "name": "Apparel", "scheme_id": scheme.json()["id"]},
    )
    assert category.status_code == 201, category.text
    assigned = await client.put(
        base + f"/product-families/{family}/categories",
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "categories": [
                {
                    "scheme_id": scheme.json()["id"],
                    "category_id": category.json()["id"],
                    "is_primary": True,
                }
            ],
        },
    )
    assert assigned.status_code == 200, assigned.text
    ready = await client.get(
        base + f"/items/{item}/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["missing"] == ["inventory_profile"]
    revisions = await client.get(base + f"/item-unit-bindings/{binding_id}/revisions", headers=auth)
    assert revisions.status_code == 200, revisions.text
    revision_id = revisions.json()["items"][0]["id"]
    quantity_body = {
        "as_of": "2090-01-01",
        "components": [
            {"unit_revision_id": revision_id, "quantity": "2"},
            {"unit_revision_id": revision_id, "quantity": "3"},
        ],
    }
    quantity = await client.post(
        base + f"/items/{item}/quantity-preview", headers=auth, json=quantity_body
    )
    assert quantity.status_code == 200, quantity.text
    assert Decimal(quantity.json()["base_quantity"]) == Decimal("5")
    for invalid_component in (
        {"quantity": "0"},
        {"quantity": "0.5"},
        {"quantity": 2.5},
        {"quantity": "1", "measured_base_quantity": "3"},
    ):
        invalid_quantity = await client.post(
            base + f"/items/{item}/quantity-preview",
            headers=auth,
            json={
                "as_of": "2090-01-01",
                "components": [{"unit_revision_id": revision_id, **invalid_component}],
            },
        )
        assert invalid_quantity.status_code == 422, invalid_quantity.text
    historical = await client.post(
        base + f"/items/{item}/quantity-preview",
        headers=auth,
        json={**quantity_body, "as_of": "2089-01-01"},
    )
    assert historical.status_code == 409, historical.text
    # A referenced category's identity cannot change underneath the product.
    referenced = await client.patch(
        base + "/item-categories/" + category.json()["id"],
        headers=command_headers(auth),
        json={"expected_version": 1, "code": "REPLACED"},
    )
    assert referenced.status_code == 409, referenced.text
    renamed = await client.patch(
        base + "/item-categories/" + category.json()["id"],
        headers=command_headers(auth),
        json={"expected_version": 1, "name": "Renamed"},
    )
    assert renamed.status_code == 200, renamed.text
    changed_pack = await client.post(
        base + f"/items/{item}/unit-revisions",
        headers=command_headers(auth),
        json={
            **binding,
            "binding_id": binding_id,
            "expected_version": 3,
            "quantity_increment": "2",
            "valid_from": "2091-01-01",
        },
    )
    assert changed_pack.status_code == 409, changed_pack.text
    new_revision = await client.post(
        base + f"/items/{item}/unit-revisions",
        headers=command_headers(auth),
        json={
            **binding,
            "binding_id": binding_id,
            "expected_version": 3,
            "valid_from": "2091-01-01",
        },
    )
    assert new_revision.status_code == 200, new_revision.text
    expired_quantity = await client.post(
        base + f"/items/{item}/quantity-preview",
        headers=auth,
        json={**quantity_body, "as_of": "2091-01-01"},
    )
    assert (
        expired_quantity.status_code == 409 and "not effective" in expired_quantity.text
    ), expired_quantity.text
    revisions = await client.get(
        base + f"/item-unit-bindings/{binding_id}/revisions",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert len(revisions.json()["items"]) == 1
    assert revisions.json()["items"][0]["valid_to"] == "2090-12-31"
    barcode_page = await client.get(base + f"/items/{item}/barcodes", headers=auth)
    barcode_id = barcode_page.json()["items"][0]["id"]
    for expected_version, active in ((4, False), (5, True)):
        state = await client.post(
            base + f"/items/{item}/barcode-state",
            headers=command_headers(auth),
            json={
                "expected_version": expected_version,
                "barcode_id": barcode_id,
                "is_active": active,
            },
        )
        assert state.status_code == 200, state.text
        if not active:
            retired_pack_change = await client.post(
                base + f"/items/{item}/unit-revisions",
                headers=command_headers(auth),
                json={
                    **binding,
                    "binding_id": binding_id,
                    "expected_version": 5,
                    "quantity_increment": "2",
                    "valid_from": "2092-01-01",
                },
            )
            assert retired_pack_change.status_code == 409, retired_pack_change.text
    await policy(factory, tenant_a, company, user, "catalog.item_barcode", "value", "read")
    page = await client.get(base + f"/items/{item}/barcodes", headers=auth)
    assert page.status_code == 200, page.text
    assert "value" not in page.json()["items"][0]


async def test_explicit_variants_are_unique_and_atomic(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    base = f"/v1/companies/{company}"
    family = product["family"]["id"]
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
    body = {
        "expected_version": 1,
        "attributes": [
            {
                "definition_id": definition,
                "is_axis": True,
                "is_required": True,
                "position": 0,
                "options": [blue, str(red_id)],
            }
        ],
        "expected_default_item_version": 1,
        "default_item_attributes": [
            {"definition_id": definition, "option_id": blue, "value_type": "TEXT"}
        ],
    }
    result = await client.put(
        base + f"/product-families/{family}/attributes", headers=command_headers(auth), json=body
    )
    assert result.status_code == 200, result.text
    variant: dict[str, Any] = {
        "expected_version": 2,
        "item": {
            "sku": "RED-SKU",
            "name": "Red product",
            "base_unit_id": product["default_item"]["base_unit_id"],
        },
        "attributes": [
            {"definition_id": definition, "option_id": str(red_id), "value_type": "TEXT"}
        ],
    }
    receipt = command_headers(auth)
    created = await client.post(
        base + f"/product-families/{family}/variants", headers=receipt, json=variant
    )
    assert created.status_code == 200, created.text
    assert (
        await client.post(
            base + f"/product-families/{family}/variants", headers=receipt, json=variant
        )
    ).headers["Idempotency-Replayed"] == "true"
    duplicate = {**variant, "expected_version": 3, "item": {**variant["item"], "sku": "DUPLICATE"}}
    response = await client.post(
        base + f"/product-families/{family}/variants", headers=command_headers(auth), json=duplicate
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert set(await db.scalars(select(Item.sku).where(Item.company_id == company))) == {
                "SKU1",
                "RED-SKU",
            }
    listing = await client.get(
        base + f"/items/{created.json()['item_id']}/attributes", headers=auth
    )
    assert listing.status_code == 200, listing.text
    assert "value_text" not in listing.json()["items"][0]
    changed_option = await client.patch(
        base + f"/attribute-options/{red_id}",
        headers=command_headers(auth),
        json={"expected_version": 1, "value_text": "Green"},
    )
    assert changed_option.status_code == 409, changed_option.text


async def test_service_configuration_adoption_and_stale_preview(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a, service=True)
    base = f"/v1/companies/{company}"
    family = product["family"]["id"]
    item = product["default_item"]["id"]
    group = await client.post(
        base + "/item-groups",
        headers=command_headers(auth),
        json={
            "code": "SERVICES",
            "name": "Services",
            "allowed_kind": "SERVICE",
            "valid_from": "2090-01-01",
        },
    )
    assert group.status_code == 201, group.text
    assigned = await client.post(
        base + f"/product-families/{family}/groups",
        headers=command_headers(auth),
        json={"expected_version": 1, "group_id": group.json()["id"], "valid_from": "2090-01-01"},
    )
    assert assigned.status_code == 200, assigned.text
    result = await client.post(
        base + f"/items/{item}/unit-bindings",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "code": "BASE",
            "unit_id": product["default_item"]["base_unit_id"],
            "role": "BASE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 2,
            "quantity_increment": "0.25",
            "fractional_entry": True,
            "valid_from": "2090-01-01",
        },
    )
    assert result.status_code == 200, result.text
    scope_id, first_revision = await publish_configuration(
        client, base, auth, options={"barcode_mode": "OPTIONAL", "barcode_default": False}
    )
    preview = await client.get(
        base + f"/items/{item}/configuration-adoption/preview",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligible"] is True
    token = preview.json()["preview_token"]
    assert (
        await client.patch(
            base + f"/items/{item}",
            headers=command_headers(auth),
            json={"expected_version": 2, "name": "Changed"},
        )
    ).status_code == 200
    stale = await client.post(
        base + f"/items/{item}/configuration-adoption",
        headers=command_headers(auth),
        json={"expected_version": 3, "as_of": "2090-01-01", "preview_token": token},
    )
    assert stale.status_code == 409, stale.text
    preview = await client.get(
        base + f"/items/{item}/configuration-adoption/preview",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    receipt = command_headers(auth)
    body = {
        "expected_version": 3,
        "as_of": "2090-01-01",
        "preview_token": preview.json()["preview_token"],
    }
    adopted = await client.post(
        base + f"/items/{item}/configuration-adoption", headers=receipt, json=body
    )
    assert adopted.status_code == 200, adopted.text
    assert (
        await client.post(
            base + f"/items/{item}/configuration-adoption", headers=receipt, json=body
        )
    ).headers["Idempotency-Replayed"] == "true"
    current = await client.get(
        base + f"/items/{item}/configuration", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert current.status_code == 200, current.text
    assert current.json()["activation_available"] is True
    assert current.json()["sources"][0]["revision_id"] == first_revision["id"]
    _, second_revision = await publish_configuration(
        client,
        base,
        auth,
        scope_id=scope_id,
        effective_from="2091-01-01",
        options={"barcode_mode": "REQUIRED"},
    )
    unchanged = await client.get(
        base + f"/items/{item}/configuration", headers=auth, params={"as_of": "2091-01-01"}
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["sources"][0]["revision_id"] == first_revision["id"]
    proposed = await client.get(
        base + f"/items/{item}/configuration-adoption/preview",
        headers=auth,
        params={"as_of": "2091-01-01"},
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["missing"] == ["barcode"]
    rejected = await client.post(
        base + f"/items/{item}/configuration-adoption",
        headers=command_headers(auth),
        json={
            "expected_version": 4,
            "as_of": "2091-01-01",
            "preview_token": proposed.json()["preview_token"],
        },
    )
    assert rejected.status_code == 409, rejected.text
    added = await client.post(
        base + f"/items/{item}/barcodes",
        headers=command_headers(auth),
        json={"expected_version": 4, "value": "SERVICE-BOOKING", "symbology": "QR"},
    )
    assert added.status_code == 200, added.text
    proposed = await client.get(
        base + f"/items/{item}/configuration-adoption/preview",
        headers=auth,
        params={"as_of": "2091-01-01"},
    )
    assert proposed.json()["eligible"] is True
    applied = await client.post(
        base + f"/items/{item}/configuration-adoption",
        headers=command_headers(auth),
        json={
            "expected_version": 5,
            "as_of": "2091-01-01",
            "preview_token": proposed.json()["preview_token"],
        },
    )
    assert applied.status_code == 200, applied.text
    changed = await client.get(
        base + f"/items/{item}/configuration", headers=auth, params={"as_of": "2091-01-01"}
    )
    assert changed.json()["sources"][0]["revision_id"] == second_revision["id"]
    adoptions = await client.get(base + f"/items/{item}/configuration-adoptions", headers=auth)
    assert adoptions.status_code == 200 and len(adoptions.json()["items"]) == 2
    adoption_id = adoptions.json()["items"][0]["id"]
    sources = await client.get(
        base + f"/product-configuration-adoptions/{adoption_id}/sources", headers=auth
    )
    assert sources.status_code == 200 and len(sources.json()["items"]) == 1


@pytest.mark.parametrize(
    "entity,field,route,body",
    [
        (
            "catalog.family_group_assignment",
            "group_id",
            "groups",
            {"group_id": str(uuid7()), "valid_from": "2090-01-01"},
        ),
        (
            "catalog.family_manufacturer",
            "manufacturer_id",
            "manufacturers",
            {"manufacturer_id": str(uuid7()), "valid_from": "2090-01-01"},
        ),
    ],
)
async def test_child_write_denies_precede_reference_lookups(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    entity: str,
    field: str,
    route: str,
    body: dict[str, Any],
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a)
    await policy(factory, tenant_a, company, user, entity, field, "write")
    response = await client.post(
        f"/v1/companies/{company}/product-families/{product['family']['id']}/{route}",
        headers=command_headers(auth),
        json={"expected_version": 1, **body},
    )
    assert response.status_code == 403, response.text
