"""Company defaults must survive preview/adoption and every subsequent consumer."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductConfigurationAdoption, ProductFamily, ProductTypeRevision
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision
from tests.commercial_factories import reference_data
from tests.configuration_factories import publish_configuration, setup_configuration
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.warranty_factories import seed_policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_adoption_resolution_marker_is_server_controlled_in_metadata(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.product_configuration_adoption/field-set",
        headers=auth,
        params={"operation": "create"},
    )
    assert response.status_code == 200, response.text
    marker = next(
        field for field in response.json()["fields"] if field["key"] == "resolution_version"
    )
    assert not marker["writable"]


@pytest.mark.parametrize("mode", ["VALUE", "CLEAR"])
async def test_company_profile_adoption_matches_review_and_retains_old_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    mode: str,
) -> None:
    await reference_data(factory)
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    _, original_id = await seed_policy(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            original = await db.get(WarrantyPolicyRevision, original_id)
            assert original is not None
            original.published_at = utcnow()
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            product_type = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert product_type is not None
            product_type.inventory_modes = ["NON_STOCK"]
            product_type.warranty_revision_id = original_id
            warranty_policy = WarrantyPolicy(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=company,
                code="COMPANY",
                name="Company warranty",
            )
            db.add(warranty_policy)
            await db.flush()
            replacement = WarrantyPolicyRevision(
                tenant_id=tenant_a,
                company_id=company,
                policy_id=warranty_policy.id,
                revision=1,
                duration=6,
                duration_unit="MONTHS",
                start_trigger="SALE",
                published_at=utcnow(),
            )
            db.add(replacement)
            await db.flush()
            replacement_id = str(replacement.id)
    expected = replacement_id if mode == "VALUE" else None
    profiles = {"warranty_revision_mode": mode}
    if mode == "VALUE":
        profiles["warranty_revision_id"] = replacement_id
    await publish_configuration(
        client,
        root,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
        profiles=profiles,
        numeric_defaults=[
            {
                "dimension": "COUNT",
                "quantity_decimal_places": 0,
                "quantity_increment": "1",
                "price_decimal_places": 2,
                "price_increment": "0.01",
                "currency": "INR",
                "price_basis_quantity": "1",
            }
        ],
    )
    path = root + f"/items/{ids['item']}"
    current = await client.get(
        root + "/product-configuration/effective",
        headers=auth,
        params={"as_of": "2091-01-01", "kind": "GOODS", "item_id": str(ids["item"])},
    )
    assert current.status_code == 200, current.text
    assert current.json()["profiles"]["warranty_revision_id"] == expected
    preview = await client.get(
        path + "/configuration-adoption/preview", headers=auth, params={"as_of": "2091-01-01"}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    assert preview.json()["resolution_version"] == 2
    injected = await client.post(
        path + "/configuration-adoption",
        headers=command_headers(auth),
        json={
            "expected_version": preview.json()["expected_version"],
            "as_of": "2091-01-01",
            "preview_token": preview.json()["preview_token"],
            "resolution_version": 1,
        },
    )
    assert injected.status_code == 422, injected.text
    result = await client.post(
        path + "/configuration-adoption",
        headers=command_headers(auth),
        json={
            "expected_version": preview.json()["expected_version"],
            "as_of": "2091-01-01",
            "preview_token": preview.json()["preview_token"],
        },
    )
    assert result.status_code == 200, result.text
    pinned = await client.get(path + "/configuration", headers=auth, params={"as_of": "2091-01-01"})
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["profiles"]["warranty_revision_id"] == expected
    defaults = await client.get(
        root + "/product-configuration/authoring-defaults",
        headers=auth,
        params={
            "as_of": "2091-01-01",
            "kind": "GOODS",
            "item_id": str(ids["item"]),
            "unit_revision_id": str(ids["item_unit_revision"]),
            "currency": "INR",
        },
    )
    assert defaults.status_code == 200, defaults.text
    assert defaults.json()["configuration"]["profiles"]["warranty_revision_id"] == expected
    assert defaults.json()["quantity"]["quantity_increment"] == "1.0000"
    assert defaults.json()["quantity"]["quantity_decimal_places"] == 0
    assert defaults.json()["price"]["price_decimal_places"] == 2
    assert defaults.json()["price"]["price_increment"] == "0.0100"
    readiness = await client.get(
        path + "/requirements", headers=auth, params={"as_of": "2091-01-01"}
    )
    assert readiness.status_code == 200 and readiness.json()["missing"] == [], readiness.text
    old = await client.get(path + "/configuration", headers=auth, params={"as_of": "2090-01-01"})
    assert old.status_code == 200, old.text
    assert old.json()["profiles"]["warranty_revision_id"] == str(original_id)
    history = await client.get(path + "/configuration-adoptions", headers=auth)
    assert history.status_code == 200, history.text
    by_revision = {row["revision"]: row for row in history.json()["items"]}
    assert {revision: row["resolution_version"] for revision, row in by_revision.items()} == {
        1: 1,
        2: 2,
    }
    latest_id = uuid.UUID(by_revision[2]["id"])
    await publish_configuration(
        client,
        root,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2092-01-01",
        profiles={"warranty_revision_mode": "INHERIT"},
    )
    future = await client.get(path + "/configuration", headers=auth, params={"as_of": "2092-01-01"})
    assert future.status_code == 200, future.text
    assert future.json()["profiles"]["warranty_revision_id"] == expected
    async with changed(
        factory, tenant_a, ProductConfigurationAdoption, latest_id, resolution_version=3
    ):
        unknown = await client.get(
            path + "/configuration", headers=auth, params={"as_of": "2092-01-01"}
        )
        assert unknown.status_code == 409, unknown.text
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.product_configuration_adoption",
        "resolution_version",
        "read",
    )
    protected = await client.get(
        path + "/configuration", headers=auth, params={"as_of": "2092-01-01"}
    )
    assert protected.status_code == 403, protected.text


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_company_publication_validates_the_configured_default_type(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
) -> None:
    company, _, auth, product = await setup_configuration(factory, tenant_a)
    root = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(product["product_type_revision_id"])
            )
            assert revision is not None
            revision.require_brand = True
            revision.kind = kind
    draft = await client.post(
        root + "/product-configurations/company",
        headers=command_headers(auth),
        json={
            "effective_from": "2090-01-01",
            "change_reason": "Incompatible default type",
            "profiles": {
                kind.lower() + "_type_revision_mode": "VALUE",
                kind.lower() + "_type_revision_id": product["product_type_revision_id"],
            },
            "options": {"brand_mode": "DISABLED"},
        },
    )
    assert draft.status_code == 201, draft.text
    preview = await client.get(
        root + "/product-configurations/" + draft.json()["id"] + "/preview", headers=auth
    )
    assert preview.status_code == 422, preview.text
    publish = await client.post(
        root + "/product-configurations/" + draft.json()["id"] + "/publish",
        headers=command_headers(auth),
        json={"expected_version": draft.json()["row_version"]},
    )
    assert publish.status_code == 422, publish.text
