import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductTypeRevision
from tests.configuration_factories import publish_configuration
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_company_configuration_keeps_native_context_and_rejects_retired_owners(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a)
    base = f"/v1/companies/{company}"
    family, item = product["family"]["id"], product["default_item"]["id"]
    async with factory() as db:
        with tenant_scope(tenant_a):
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(product["family"]["product_type_revision_id"])
            )
            assert revision is not None
            type_id = str(revision.product_type_id)
    group = await client.post(
        base + "/item-groups",
        headers=command_headers(auth),
        json={
            "code": "GROUP",
            "name": "Group",
            "allowed_kind": "GOODS",
            "valid_from": "2090-01-01",
        },
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]
    assignment = await client.post(
        base + f"/product-families/{family}/groups",
        headers=command_headers(auth),
        json={"expected_version": 1, "group_id": group_id, "valid_from": "2090-01-01"},
    )
    assert assignment.status_code == 200, assignment.text
    definitions = [
        {"scope_kind": "COMPANY"},
        {"scope_kind": "TYPE", "product_type_id": type_id},
        {"scope_kind": "GROUP", "group_id": group_id},
        {"scope_kind": "FAMILY", "family_id": family},
        {"scope_kind": "SKU", "item_id": item},
    ]
    scope_id, _ = await publish_configuration(
        client,
        base,
        auth,
        options={"barcode_mode": "OPTIONAL", "barcode_default": False, "brand_mode": "DISABLED"},
        numeric_defaults=[
            {"dimension": "COUNT", "quantity_decimal_places": 0, "quantity_increment": "1"}
        ],
    )
    for retired in definitions[1:]:
        refused = await client.post(
            base + "/product-configuration-scopes", headers=command_headers(auth), json=retired
        )
        assert refused.status_code == 422, refused.text
    query = {"as_of": "2090-01-01", "kind": "GOODS", "item_id": item}
    effective = await client.get(
        base + "/product-configuration/effective", headers=auth, params=query
    )
    assert effective.status_code == 200, effective.text
    value = effective.json()
    assert [row["scope_kind"] for row in value["sources"]] == ["COMPANY"]
    assert value["options"]["barcode_default"] is False
    assert value["numeric_defaults"][0]["quantity_increment"] == "1.0000"
    from tests.product_review_factories import changed

    async with changed(
        factory,
        tenant_a,
        ProductTypeRevision,
        uuid.UUID(product["family"]["product_type_revision_id"]),
        require_brand=True,
    ):
        conflict = await client.get(
            base + "/product-configuration/effective", headers=auth, params=query
        )
        assert conflict.status_code == 422, conflict.text
    await publish_configuration(
        client,
        base,
        auth,
        scope_id=scope_id,
        effective_from="2091-01-01",
        options={"barcode_mode": "REQUIRED"},
    )
    # Owner permissions also constrain the global scope list and its filter.
    readonly = headers(
        company, tenant=tenant_a, user=user, permission=["product_configuration.read"]
    )
    page = await client.get(base + "/product-configuration-scopes", headers=readonly)
    assert page.status_code == 200, page.text
    assert [row["scope_kind"] for row in page.json()["items"]] == ["COMPANY"]
    denied = await client.get(
        base + "/product-configuration-scopes", headers=readonly, params={"scope_kind": "SKU"}
    )
    assert denied.status_code == 422, denied.text
    revisions = await client.get(
        base + f"/product-configuration-scopes/{scope_id}/revisions",
        headers=auth,
        params={"effective_on": "2090-01-01"},
    )
    assert revisions.status_code == 200 and len(revisions.json()["items"]) == 1


async def test_native_definition_routes_require_actor_company_and_current_field_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a, service=True)
    other, _, foreign, _ = await create_product(client, factory, tenant_a, service=True)
    family, item = product["family"]["id"], product["default_item"]["id"]
    base = f"/v1/companies/{company}"
    no_permissions = headers(company, tenant=tenant_a, user=user, permission=[])
    routes = [
        f"/product-families/{family}/{part}"
        for part in ("groups", "categories", "manufacturers", "attributes", "attribute-options")
    ]
    routes += [
        f"/items/{item}/{part}"
        for part in ("attributes", "unit-bindings", "barcodes", "configuration-adoptions")
    ]
    for route in routes:
        assert (await client.get(base + route)).status_code == 401
        assert (await client.get(base + route, headers=no_permissions)).status_code == 403
        wrong_company = await client.get(f"/v1/companies/{other}" + route, headers=foreign)
        assert wrong_company.status_code == 403, wrong_company.text
        invalid = await client.get(base + route, headers=auth, params={"offset": 1})
        assert invalid.status_code == 422, invalid.text
    barcode_path = base + f"/items/{item}/barcodes"
    receipt = command_headers(auth)
    body = {"expected_version": 1, "value": "EXACT-001", "symbology": "CODE128"}
    created = await client.post(barcode_path, headers=receipt, json=body)
    assert created.status_code == 200, created.text
    await policy(factory, tenant_a, company, user, "catalog.item_barcode", "value", "write")
    replay = await client.post(barcode_path, headers=receipt, json=body)
    assert replay.status_code == 403, replay.text
