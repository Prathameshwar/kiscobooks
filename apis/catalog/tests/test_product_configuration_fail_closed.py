import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    Item,
    ItemGroup,
    ProductFamily,
    ProductType,
    ProductTypeRevision,
)
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_effective_sources_fail_closed_for_wrong_owners_and_broken_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    other, foreign = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    route = base + "/product-configuration/effective"
    params = {"as_of": "2090-01-01", "kind": "GOODS", "item_id": str(ids["item"])}
    for overrides, status in (
        ({"kind": "SERVICE"}, 409),
        ({"family_id": str(foreign["product_family"])}, 403),
        ({"item_id": str(foreign["item"])}, 403),
        ({"group_id": str(foreign["item_group"])}, 403),
    ):
        response = await client.get(route, headers=auth, params={**params, **overrides})
        assert response.status_code == status, response.text

    async def alter(model: type[Any], key: uuid.UUID, field: str, value: Any) -> Any:
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                row = await db.get(model, key)
                assert row is not None
                previous = getattr(row, field)
                setattr(row, field, value)
                return previous

    with tenant_scope(tenant_a):
        async with factory() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            revision_id = family.product_type_revision_id
            revision = await db.get(ProductTypeRevision, revision_id)
            assert revision is not None
            type_id = revision.product_type_id
    model: type[Any]
    value: Any
    for model, key, field, value, overrides in (
        (ProductType, type_id, "is_active", False, {}),
        (ProductTypeRevision, revision_id, "published_at", None, {}),
        (
            ItemGroup,
            ids["item_group"],
            "allowed_kind",
            "SERVICE",
            {"group_id": str(ids["item_group"])},
        ),
    ):
        old = await alter(model, key, field, value)
        try:
            response = await client.get(route, headers=auth, params={**params, **overrides})
            assert response.status_code == 409, response.text
        finally:
            await alter(model, key, field, old)
    # Barcode maintenance permits ACTIVE SKUs (barcode-delivery-plan.md), but cannot
    # bypass discontinued products/families or exhausted versions. Active structural
    # configuration adoption is separately covered by test_product_adoption_boundaries.
    item_path = base + f"/items/{ids['item']}/barcodes"
    barcode = {"value": "NEW", "symbology": "CODE128"}
    for model, key, field, value, expected in (
        (Item, ids["item"], "status", "DISCONTINUED", 1),
        (ProductFamily, ids["product_family"], "status", "DISCONTINUED", 1),
        (Item, ids["item"], "row_version", 2147483647, 2147483647),
    ):
        old = await alter(model, key, field, value)
        try:
            response = await client.post(
                item_path,
                headers=command_headers(auth),
                json={"expected_version": expected, **barcode},
            )
            assert response.status_code == 409, response.text
        finally:
            await alter(model, key, field, old)
    # An ACTIVE family still refuses structural configuration adoption on its ACTIVE SKU.
    old_family = await alter(ProductFamily, ids["product_family"], "status", "ACTIVE")
    old_item = await alter(Item, ids["item"], "status", "ACTIVE")
    try:
        adoption_path = base + f"/items/{ids['item']}/configuration-adoption"
        preview = await client.get(
            adoption_path + "/preview", headers=auth, params={"as_of": "2090-01-01"}
        )
        assert preview.status_code == 200, preview.text
        assert not preview.json()["eligible"]
        assert "active_structural_adoption_unsupported" in preview.json()["blocked_reasons"]
        response = await client.post(
            adoption_path,
            headers=command_headers(auth),
            json={
                "expected_version": 1,
                "as_of": "2090-01-01",
                "preview_token": preview.json()["preview_token"],
            },
        )
        assert response.status_code == 409, response.text
    finally:
        await alter(Item, ids["item"], "status", old_item)
    # ... but accepts authoring of a DRAFT SKU in it (docs/catalog-attributes-api.md:
    # active families "accept new DRAFT variants and authoring of those drafts").
    try:
        response = await client.post(
            item_path, headers=command_headers(auth), json={"expected_version": 1, **barcode}
        )
        assert response.status_code == 200, response.text
        assert response.json()["item_version"] == 2
    finally:
        await alter(ProductFamily, ids["product_family"], "status", old_family)
    for version, (entity_name, field) in enumerate(
        (
            ("catalog.product_configuration_revision", "effective_from"),
            ("catalog.product_configuration_scope", "owner_id"),
        ),
        3,
    ):
        await policy(
            factory,
            tenant_a,
            company,
            ids["actor_user"],
            entity_name,
            field,
            "read",
            version=version,
        )
        response = await client.get(route, headers=auth, params=params)
        assert response.status_code == 403, response.text
