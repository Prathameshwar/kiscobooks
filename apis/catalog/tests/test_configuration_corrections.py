"""Regression tests for configuration editing and persisted product context."""

import uuid

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.configuration_factories import publish_configuration
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_existing_sku_derives_its_dated_group(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    await publish_configuration(
        client,
        base,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
        options={"barcode_mode": "DISABLED"},
    )
    params = {"as_of": "2091-01-01", "kind": "GOODS", "item_id": str(ids["item"])}
    inferred = await client.get(
        base + "/product-configuration/effective", headers=auth, params=params
    )
    explicit = await client.get(
        base + "/product-configuration/effective",
        headers=auth,
        params={**params, "group_id": str(ids["item_group"])},
    )
    assert inferred.status_code == explicit.status_code == 200
    assert inferred.json()["options"] == explicit.json()["options"]
    assert inferred.json()["options"]["barcode_mode"] == "DISABLED"
    historical = await client.get(
        base + "/product-configuration/effective",
        headers=auth,
        params={**params, "as_of": "2090-01-01"},
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["options"]["barcode_mode"] == "OPTIONAL"
    inconsistent = await client.get(
        base + "/product-configuration/effective",
        headers=auth,
        params={**params, "group_id": str(uuid.uuid4())},
    )
    assert inconsistent.status_code == 403, inconsistent.text

    from tests.test_master_reference_policy import policy

    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.family_group_assignment",
        "group_id",
        "read",
    )
    denied = await client.get(
        base + "/product-configuration/effective", headers=auth, params=params
    )
    assert denied.status_code == 403, denied.text


async def test_nested_patch_preserves_siblings_and_resets_only_explicit_choices(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    created = await client.post(
        base + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": str(ids["product_configuration_scope"]),
            "effective_from": "2091-01-01",
            "change_reason": "Initial",
            "options": {
                "barcode_mode": "REQUIRED",
                "brand_mode": "OPTIONAL",
                "brand_default": True,
            },
            "pricing": {"sale_price_mode": "REQUIRED", "mrp_mode": "REQUIRED"},
        },
    )
    assert created.status_code == 201, created.text
    path = base + "/product-configurations/" + created.json()["id"]
    response = await client.patch(
        path,
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "options": {"brand_mode": "DISABLED"},
            "pricing": {"mrp_mode": "INHERIT"},
        },
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["options"]["barcode_mode"] == "REQUIRED"
    assert value["options"]["brand_mode"] == "DISABLED"
    assert value["options"]["brand_default"] is None
    assert value["pricing"]["sale_price_mode"] == "REQUIRED"
    assert value["pricing"]["mrp_mode"] == "INHERIT"
    response = await client.patch(
        path,
        headers=command_headers(auth),
        json={"expected_version": 2, "options": {"brand_mode": "OPTIONAL", "brand_default": True}},
    )
    assert response.status_code == 200, response.text
    response = await client.patch(
        path,
        headers=command_headers(auth),
        json={"expected_version": 3, "options": {"brand_default": False}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["options"]["brand_mode"] == "OPTIONAL"
    assert response.json()["options"]["brand_default"] is False
    assert response.json()["options"]["barcode_mode"] == "REQUIRED"


async def test_shared_goods_defaults_are_inapplicable_to_services(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    await publish_configuration(
        client,
        base,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
        options={"manufacturer_mode": "REQUIRED"},
        pricing={"mrp_mode": "REQUIRED"},
    )
    response = await client.get(
        base + "/product-configuration/effective",
        headers=auth,
        params={"as_of": "2091-01-01", "kind": "SERVICE"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["options"]["manufacturer_mode"] == "DISABLED"
    assert response.json()["pricing"]["mrp_mode"] == "DISABLED"
    metadata = {row["field"]: row for row in response.json()["settings"]}
    assert metadata["options.manufacturer"]["applicable"] is False


async def test_preview_explains_changes_and_sources(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    created = await client.post(
        base + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": str(ids["product_configuration_scope"]),
            "effective_from": "2091-01-01",
            "change_reason": "Require barcode",
            "options": {"barcode_mode": "REQUIRED"},
        },
    )
    assert created.status_code == 201, created.text
    response = await client.get(
        base + "/product-configurations/" + created.json()["id"] + "/preview", headers=auth
    )
    assert response.status_code == 200, response.text
    views = response.json()["comparisons"]
    assert {view["kind"] for view in views} == {"GOODS", "SERVICE"}
    for view in views:
        assert "options.barcode_mode" in view["changed_fields"]
        assert view["before"]["options"]["barcode_mode"] == "OPTIONAL"
        assert view["after"]["options"]["barcode_mode"] == "REQUIRED"
        setting = next(
            row for row in view["after"]["settings"] if row["field"] == "options.barcode"
        )
        assert setting["overrideable"] is False
        assert setting["origins"][0]["kind"] == "DRAFT"


async def test_active_adoption_preview_reports_the_command_boundary(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models import Item
    from tests.product_review_factories import changed

    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    path = f"/v1/companies/{company}/items/{ids['item']}/configuration-adoption"
    async with changed(factory, tenant_a, Item, ids["item"], status="ACTIVE"):
        response = await client.get(path + "/preview", headers=auth, params={"as_of": "2090-01-01"})
        assert response.status_code == 200, response.text
        assert response.json()["eligible"] is False
        assert response.json()["blocked_reasons"] == ["active_structural_adoption_unsupported"]
        rejected = await client.post(
            path,
            headers=command_headers(auth),
            json={
                "as_of": "2090-01-01",
                "expected_version": 1,
                "preview_token": response.json()["preview_token"],
            },
        )
        assert rejected.status_code == 409, rejected.text


async def test_authoring_defaults_keep_adoption_pins_and_validate_context(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    await publish_configuration(
        client,
        root,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
        options={"brand_mode": "REQUIRED"},
    )
    path = root + "/product-configuration/authoring-defaults"
    params = {
        "kind": "GOODS",
        "as_of": "2091-01-01",
        "item_id": str(ids["item"]),
        "include_price": "false",
    }
    response = await client.get(path, headers=auth, params=params)
    assert response.status_code == 200, response.text
    assert response.json()["configuration"]["options"]["brand_mode"] == "OPTIONAL"
    for context, status in (
        ({"group_id": str(uuid.uuid4())}, 403),
        ({"family_id": str(uuid.uuid4())}, 403),
        ({"kind": "SERVICE"}, 409),
        ({"as_of": "invalid"}, 422),
    ):
        response = await client.get(path, headers=auth, params={**params, **context})
        assert response.status_code == status, response.text
    anonymous = await client.get(path, params=params)
    assert anonymous.status_code == 401, anonymous.text
    denied = await client.get(
        path,
        params=params,
        headers=headers(company, tenant=tenant_a, user=ids["actor_user"], permission=["unit.read"]),
    )
    assert denied.status_code == 403, denied.text
    foreign_company, foreign_ids = await seed_definitions(factory, tenant_a)
    foreign = await client.get(
        path, params={**params, "item_id": str(foreign_ids["item"])}, headers=auth
    )
    assert foreign_company != company
    assert foreign.status_code == 403, foreign.text

    repair = await client.post(
        root + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": str(ids["product_configuration_scope"]),
            "effective_from": "2092-01-01",
            "change_reason": "Resume company default",
            "options": {"brand_mode": "INHERIT"},
        },
    )
    assert repair.status_code == 201, repair.text
    preview_path = root + "/product-configurations/" + repair.json()["id"]
    preview = await client.get(preview_path + "/preview", headers=auth)
    assert preview.status_code == 200, preview.text
    comparison = preview.json()["comparisons"][0]
    assert comparison["before"]["options"]["brand_mode"] == "REQUIRED"
    assert not comparison["before_conflicts"]
    assert comparison["after"]["options"]["brand_mode"] == "OPTIONAL"
    published = await client.post(
        preview_path + "/publish",
        headers=command_headers(auth),
        json={
            "expected_version": preview.json()["draft_version"],
            "expected_generation": preview.json()["policy_generation"],
            "expected_source_version": preview.json()["source_version"],
        },
    )
    assert published.status_code == 201, published.text
