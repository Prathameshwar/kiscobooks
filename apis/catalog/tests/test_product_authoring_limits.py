import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import FamilyManufacturer, Item, ItemBarcode, ItemUnitBinding, ItemUnitRevision
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_definition_requirements_bound_current_rows_without_limiting_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for index in range(129):
                start = dt.date(2000, 1, 1) + dt.timedelta(days=index)
                common = {"tenant_id": tenant_a, "company_id": company}
                db.add(
                    FamilyManufacturer(
                        **common,
                        family_id=ids["product_family"],
                        manufacturer_id=ids["manufacturer"],
                        production_role="IMPORTER",
                        valid_from=start,
                        valid_to=start,
                    )
                )
                db.add(
                    ItemBarcode(
                        **common,
                        item_id=ids["item"],
                        value=f"OLD-{index}",
                        symbology="CODE128",
                        is_active=False,
                    )
                )
                db.add(
                    ItemUnitRevision(
                        **common,
                        binding_id=ids["item_unit_binding"],
                        revision=index + 2,
                        conversion_mode="FIXED",
                        numerator=1,
                        denominator=1,
                        quantity_decimal_places=0,
                        quantity_increment="1",
                        fractional_entry=False,
                        valid_from=start,
                        valid_to=start,
                    )
                )
    response = await client.get(
        f"/v1/companies/{company}/items/{ids['item']}/requirements",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["missing"] == ["inventory_profile"]


async def test_new_bindings_cannot_exceed_the_readable_authoring_bound(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None
            unit_id = item.base_unit_id
            db.add_all(
                [
                    ItemUnitBinding(
                        tenant_id=tenant_a,
                        company_id=company,
                        item_id=item.id,
                        unit_id=unit_id,
                        code=f"SALE-{index}",
                        usage_role="SALE",
                    )
                    for index in range(63)
                ]
            )
    response = await client.post(
        f"/v1/companies/{company}/items/{ids['item']}/unit-bindings",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "code": "OVERFLOW",
            "unit_id": str(unit_id),
            "role": "SALE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "valid_from": "2091-01-01",
        },
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None and item.row_version == 1


async def test_base_grid_review_rejects_oversized_legacy_alternate_definitions(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None
            unit_id = item.base_unit_id
            common = {"tenant_id": tenant_a, "company_id": company}
            for index in range(65):
                binding = ItemUnitBinding(
                    **common,
                    item_id=item.id,
                    unit_id=unit_id,
                    code=f"LEGACY-{index}",
                    usage_role="SALE",
                )
                db.add(binding)
                await db.flush()
                db.add(
                    ItemUnitRevision(
                        **common,
                        binding_id=binding.id,
                        revision=1,
                        conversion_mode="FIXED",
                        numerator=1,
                        denominator=1,
                        quantity_decimal_places=0,
                        quantity_increment="1",
                        fractional_entry=False,
                        valid_from=dt.date(2090, 1, 1),
                    )
                )
    response = await client.post(
        f"/v1/companies/{company}/items/{ids['item']}/unit-revisions",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "binding_id": str(ids["item_unit_binding"]),
            "code": "BASE",
            "unit_id": str(unit_id),
            "role": "BASE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "valid_from": "2091-01-01",
        },
    )
    assert response.status_code == 409 and "authoring bound" in response.text, response.text
    blocked = await client.get(
        f"/v1/companies/{company}/items/{ids['item']}/requirements",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert blocked.status_code == 409 and "bounded authoring" in blocked.text, blocked.text
