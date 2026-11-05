"""Initial setup commits or rolls back with the family and first SKU."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select

from catalog.models import Item, ProductFamily
from catalog.models.pricing import ItemPriceDraft
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.tasks.product_creation_review import configuration_fingerprint
from tests.pricing_factories import create, guard
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def initial(body):
    return {
        "effective_from": "2026-01-01",
        "units": [
            {
                "expected_version": 1,
                "code": "BASE",
                "unit_id": body["default_item"]["base_unit_id"],
                "role": "BASE",
                "conversion_mode": "FIXED",
                "numerator": "1",
                "denominator": "1",
                "quantity_decimal_places": 0,
                "quantity_increment": "1",
                "fractional_entry": False,
                "valid_from": "2026-01-01",
            }
        ],
    }


async def test_initial_units_are_atomic_and_idempotent(client, factory, tenant_a):
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "item.read",
            "item.create",
            "item.update",
            "unit.read",
            "product_type.read",
            "product_configuration.read",
            "brand.read",
            "brand_series.read",
        ],
    )
    body["initial_setup"] = initial(body)
    route = f"/v1/companies/{company}/product-families"
    signed = command_headers(auth)
    response = await client.post(route, headers=signed, json=body)
    assert response.status_code == 201, response.text
    replay = await client.post(route, headers=signed, json=body)
    assert replay.status_code == 201, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == response.json()
    with tenant_scope(tenant_a):
        async with factory() as db:
            for model in (ProductFamily, Item, ItemUnitBinding, ItemUnitRevision):
                assert await db.scalar(select(func.count(model.id))) == 1


@pytest.mark.parametrize("failure", ["wrong-company-unit", "invalid-ratio"])
async def test_failed_setup_leaves_no_product(client, factory, tenant_a, failure):
    company, _, auth, body = await setup_product(factory, tenant_a)
    setup = initial(body)
    if failure == "wrong-company-unit":
        _, _, _, other = await setup_product(factory, tenant_a)
        setup["units"][0]["unit_id"] = other["default_item"]["base_unit_id"]
    else:
        setup["units"][0]["numerator"] = "2"
    body["initial_setup"] = setup
    response = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert response.status_code in {403, 404, 409, 422}, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            for model in (ProductFamily, Item, ItemUnitBinding, ItemUnitRevision):
                assert await db.scalar(select(func.count(model.id))) == 0


async def test_setup_requires_native_update_authority(client, factory, tenant_a):
    company, user, _, body = await setup_product(factory, tenant_a)
    body["initial_setup"] = initial(body)
    auth = headers(company, tenant=tenant_a, user=user, permission=["item.read", "item.create"])
    response = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("source_refreshed", [False, True])
async def test_initial_price_is_a_native_exact_draft_and_replays_once(
    client, factory, tenant_a, source_refreshed
):
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    level = await create(client, root, auth, "/pricing/bootstrap", {})
    plan = await create(
        client,
        root,
        auth,
        "/price-plans",
        {
            "code": "INITIAL_SALE",
            "name": "Initial sale",
            "purpose": "SALE",
            "price_level_id": level["id"],
            "currency": "INR",
            "tax_basis": "EXCLUSIVE",
        },
    )
    setup = initial(body)
    setup["effective_from"] = setup["units"][0]["valid_from"] = "2090-01-01"
    setup.update(guard(plan))
    if source_refreshed:
        response = await client.get(
            root + "/product-configuration/effective?as_of=2090-01-01&kind=GOODS"
            "&product_type_revision_id=" + body["product_type_revision_id"],
            headers=auth,
        )
        assert response.status_code == 200, response.text
        reviewed = EffectiveConfiguration.model_validate(response.json())
        setup.update(
            {
                "expected_generation": reviewed.policy_generation,
                "expected_source_version": reviewed.source_version,
                "configuration_fingerprint": configuration_fingerprint(reviewed),
            }
        )
        await setup_source(factory, tenant_a, company, user, version=4)
    setup["prices"] = [
        {
            "plan_id": plan["id"],
            "amount": "123.4500",
            "price_basis_quantity": "1",
            "price_decimal_places": 4,
        }
    ]
    body["initial_setup"] = setup
    signed = command_headers(auth)
    result = await client.post(root + "/product-families", headers=signed, json=body)
    assert result.status_code == 201, result.text
    assert len(result.json()["price_draft_ids"]) == 1
    replay = await client.post(root + "/product-families", headers=signed, json=body)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(tenant_a):
        async with factory() as db:
            drafts = list(await db.scalars(select(ItemPriceDraft)))
            assert len(drafts) == 1
            assert str(drafts[0].amount) == "123.4500"
            assert drafts[0].status == "DRAFT"
            assert str(drafts[0].item_id) == result.json()["default_item"]["id"]
            assert str(drafts[0].id) == result.json()["price_draft_ids"][0]


async def test_stock_and_unknown_setup_are_rejected(client, factory, tenant_a):
    company, _, auth, body = await setup_product(factory, tenant_a)
    body["initial_setup"] = {**initial(body), "opening_quantity": "12", "opening_value": "120"}
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 422


@pytest.mark.parametrize("section", ["tax", "prices"])
async def test_retired_note_is_rejected_without_creating_a_product(
    client, factory, tenant_a, section
):
    import uuid

    company, _, auth, body = await setup_product(factory, tenant_a)
    setup = {**initial(body), "expected_generation": 1, "expected_source_version": 1}
    if section == "tax":
        setup[section] = {
            "rule_id": str(uuid.uuid4()),
            "directions": ["SALE"],
            "source_reference": "Retired note",
        }
    else:
        setup[section] = [
            {
                "plan_id": str(uuid.uuid4()),
                "amount": "1",
                "price_basis_quantity": "1",
                "price_decimal_places": 0,
                "source_reference": "Retired note",
            }
        ]
    body["initial_setup"] = setup
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 422, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0


async def test_denied_unit_field_rolls_back(client, factory, tenant_a):
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    body["initial_setup"] = initial(body)
    route = f"/v1/companies/{company}/product-families"
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.item_unit_revision",
        "quantity_increment",
        "write",
    )
    denied = await client.post(route, headers=command_headers(auth), json=body)
    assert denied.status_code == 403, denied.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0


async def test_successful_setup_replay_rechecks_current_field_denies(client, factory, tenant_a):
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    body["initial_setup"] = initial(body)
    route = f"/v1/companies/{company}/product-families"
    signed = command_headers(auth)
    result = await client.post(route, headers=signed, json=body)
    assert result.status_code == 201, result.text
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.item_unit_revision",
        "quantity_increment",
        "write",
    )
    replay = await client.post(route, headers=signed, json=body)
    assert replay.status_code == 403, replay.text


async def test_initial_tax_uses_native_binding_integrity(client, factory, tenant_a):
    from catalog.models.tax import CatalogTaxBinding
    from tests.tax_factories import seed_tax

    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            body = {
                "code": "INITIAL_TAX",
                "name": "Tax setup test",
                "kind": family.kind,
                "product_type_revision_id": str(family.product_type_revision_id),
                "default_item": {
                    "sku": "INITIAL_TAX",
                    "name": "Tax setup SKU",
                    "base_unit_id": str(ids["unit_of_measure"]),
                },
            }
            before = await db.scalar(select(func.count(CatalogTaxBinding.id)))
    configuration = await client.get(
        root + "/product-configuration/effective?as_of=2090-01-01&kind=GOODS", headers=auth
    )
    assert configuration.status_code == 200, configuration.text
    setup = initial(body)
    setup["effective_from"] = setup["units"][0]["valid_from"] = "2090-01-01"
    setup.update(
        {
            "expected_generation": configuration.json()["policy_generation"],
            "expected_source_version": configuration.json()["source_version"],
        }
    )
    setup["tax"] = {
        "classification_id": str(ids["tax_classification"]),
        "rule_id": str(ids["tax_rule"]),
        "directions": ["SALE"],
    }
    body["initial_setup"] = setup
    result = await client.post(root + "/product-families", headers=command_headers(auth), json=body)
    assert result.status_code == 201, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            # Classification, rule and its required treatment.
            assert await db.scalar(select(func.count(CatalogTaxBinding.id))) == before + 3


@pytest.mark.parametrize("tampered", [False, True])
async def test_reviewed_configuration_handles_source_refresh_but_rejects_changed_values(
    client, factory, tenant_a, tampered
):
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    path = (
        root
        + "/product-configuration/effective?as_of=2026-01-01&kind=GOODS&product_type_revision_id="
        + body["product_type_revision_id"]
    )
    response = await client.get(path, headers=auth)
    assert response.status_code == 200, response.text
    reviewed = EffectiveConfiguration.model_validate(response.json())
    setup = initial(body)
    setup.update(
        {
            "expected_generation": reviewed.policy_generation,
            "expected_source_version": reviewed.source_version,
            "configuration_fingerprint": "0" * 64
            if tampered
            else configuration_fingerprint(reviewed),
        }
    )
    body["initial_setup"] = setup
    await setup_source(factory, tenant_a, company, user, version=4)
    current = await client.get(path, headers=auth)
    assert current.status_code == 200, current.text
    assert current.json()["source_version"] > reviewed.source_version
    assert configuration_fingerprint(
        EffectiveConfiguration.model_validate(current.json())
    ) == configuration_fingerprint(reviewed)
    created = await client.post(
        root + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == (409 if tampered else 201), created.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == (0 if tampered else 1)
