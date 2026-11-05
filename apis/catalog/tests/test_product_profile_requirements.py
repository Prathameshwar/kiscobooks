import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CatalogDefaultProfile,
    IdentifierProfile,
    InventoryProfileTemplateRevision,
    ItemUnitRevision,
    ProductFamily,
    ProductTypeRevision,
    ReturnPolicyRevision,
)
from tests.configuration_factories import publish_configuration
from tests.inventory_factories import seed_template
from tests.product_definition_factories import seed_definitions
from tests.product_integrity_factories import features
from tests.product_review_factories import changed
from tests.profile_factories import seed_identifier_profile
from tests.return_factories import seed_policy
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_native_inventory_identifier_defaults_and_serial_readiness(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    user = ids["actor_user"]
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    base = f"/v1/companies/{company}"
    path = base + f"/items/{ids['item']}/requirements"
    _, inventory_id = await seed_template(factory, tenant_a, company)
    identifier_id = await seed_identifier_profile(factory, tenant_a, company)
    _, return_id = await seed_policy(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            inventory = await db.get(InventoryProfileTemplateRevision, inventory_id)
            returns = await db.get(ReturnPolicyRevision, return_id)
            family = await db.get(ProductFamily, ids["product_family"])
            defaults = await db.get(CatalogDefaultProfile, ids["catalog_default_profile"])
            assert (
                inventory is not None
                and returns is not None
                and family is not None
                and defaults is not None
            )
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            revision.tracking_modes = ["SERIAL"]
            inventory.published_at = returns.published_at = utcnow()
            inventory.serial_tracking = True
            inventory.identifier_profile_id = identifier_id
            defaults.inventory_template_revision_mode = "VALUE"
            defaults.inventory_template_revision_id = inventory_id
            defaults.identifier_profile_mode = "VALUE"
            defaults.identifier_profile_id = identifier_id
            defaults.return_policy_revision_mode = "VALUE"
            defaults.return_policy_revision_id = return_id
            defaults.goods_type_revision_mode = "VALUE"
            defaults.goods_type_revision_id = revision.id
            other = IdentifierProfile(
                tenant_id=tenant_a,
                company_id=company,
                code="OTHER",
                name="Other",
                normalization_version=1,
            )
            db.add(other)
            await db.flush()
            other_id = other.id
    await features(factory, tenant_a, company, user, {"serial_tracking"})
    response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
    assert response.status_code == 200 and response.json()["missing"] == [], response.text
    assert response.json()["product_definition_complete"] is True
    assert response.json()["activation_available"] is True
    service = await client.get(
        base + "/product-configuration/effective",
        headers=auth,
        params={"as_of": "2090-01-01", "kind": "SERVICE"},
    )
    assert service.status_code == 200, service.text
    service_config = service.json()
    settings = {row["field"]: row for row in service_config["settings"]}
    for field in (
        "goods_type_revision",
        "inventory_template_revision",
        "handling_revision",
        "identifier_profile",
    ):
        assert service_config["profiles"][field + "_id"] is None
        assert settings["profiles." + field]["applicable"] is False
        assert settings["profiles." + field]["overrideable"] is False
    assert service_config["profiles"]["return_policy_revision_id"] == str(return_id)
    async with changed(
        factory,
        tenant_a,
        ItemUnitRevision,
        ids["item_unit_revision"],
        quantity_decimal_places=1,
        fractional_entry=True,
    ):
        response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
        assert response.status_code == 200 and response.json()["missing"] == [
            "integer_serial_base_quantity"
        ], response.text
    async with changed(
        factory,
        tenant_a,
        CatalogDefaultProfile,
        ids["catalog_default_profile"],
        identifier_profile_id=other_id,
    ):
        response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
        assert (
            response.status_code == 409 and "identifier selection differs" in response.text
        ), response.text
    async with changed(
        factory,
        tenant_a,
        CatalogDefaultProfile,
        ids["catalog_default_profile"],
        inventory_template_revision_mode="CLEAR",
        inventory_template_revision_id=None,
    ):
        response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
        assert response.status_code == 200 and response.json()["missing"] == [
            "inventory_profile"
        ], response.text
    # Losing the company capability invalidates both resolution and new draft selection.
    facts = tuple(row for row in all_facts(company, user) if row.kind != "feature")
    await setup_source(factory, tenant_a, company, user, version=4, facts=facts)
    response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
    assert (
        response.status_code == 409 and "enabled company inventory" in response.text
    ), response.text
    draft = await client.post(
        base + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": str(ids["product_configuration_scope"]),
            "effective_from": "2091-01-01",
            "change_reason": "No capability",
            "profiles": {
                "inventory_template_revision_mode": "VALUE",
                "inventory_template_revision_id": str(inventory_id),
            },
        },
    )
    assert draft.status_code == 409 and "enabled company inventory" in draft.text, draft.text
    for version, entity, field in (
        (5, "identifier_profile_requirement", "min_count"),
        (6, "return_policy_condition", "condition_code"),
    ):
        await policy(
            factory, tenant_a, company, user, "catalog." + entity, field, "read", version=version
        )
        response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
        assert response.status_code == 403, response.text


async def test_nonserialized_goods_and_not_yet_effective_bindings_have_distinct_readiness(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    _, inventory_id = await seed_template(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            inventory = await db.get(InventoryProfileTemplateRevision, inventory_id)
            defaults = await db.get(CatalogDefaultProfile, ids["catalog_default_profile"])
            assert inventory is not None and defaults is not None
            inventory.published_at = utcnow()
            defaults.inventory_template_revision_mode = "VALUE"
            defaults.inventory_template_revision_id = inventory_id
    path = f"/v1/companies/{company}/items/{ids['item']}/requirements"
    ready = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
    assert ready.status_code == 200 and ready.json()["missing"] == [], ready.text
    historical = await client.get(path, headers=auth, params={"as_of": "2089-01-01"})
    assert historical.status_code == 200, historical.text
    assert "base_unit_binding" in historical.json()["missing"]


async def test_available_pricing_and_inventory_capabilities_publish_for_company_default_type(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    user = ids["actor_user"]
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    _, inventory_id = await seed_template(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            inventory = await db.get(InventoryProfileTemplateRevision, inventory_id)
            family = await db.get(ProductFamily, ids["product_family"])
            assert inventory is not None and family is not None
            inventory.published_at = utcnow()
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            type_revision_id = revision.id
    feature = SnapshotRecord(
        kind="feature",
        id=uuid7(),
        data={
            "company_id": str(company),
            "feature_key": "multi_price_levels",
            "is_enabled": True,
            "locked_at": None,
        },
    )
    await setup_source(
        factory, tenant_a, company, user, version=3, facts=(*all_facts(company, user), feature)
    )
    _, published = await publish_configuration(
        client,
        root,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
        profiles={
            "goods_type_revision_mode": "VALUE",
            "goods_type_revision_id": str(type_revision_id),
            "inventory_template_revision_mode": "VALUE",
            "inventory_template_revision_id": str(inventory_id),
        },
        pricing={"sale_level_count": 3},
    )
    assert published["pricing"]["sale_level_count"] == 3
    await policy(
        factory, tenant_a, company, user, "catalog.product_type", "name", "read", version=4
    )
    scopes = await client.get(root + "/product-configuration-scopes", headers=auth)
    assert scopes.status_code == 200, scopes.text
    assert [row["scope_kind"] for row in scopes.json()["items"]] == ["COMPANY"]
    await policy(
        factory, tenant_a, company, user, "catalog.unit_of_measure", "name", "read", version=5
    )
    denied = await client.post(
        root + f"/items/{ids['item']}/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [{"unit_revision_id": str(ids["item_unit_revision"]), "quantity": "1"}],
        },
    )
    assert denied.status_code == 403, denied.text
