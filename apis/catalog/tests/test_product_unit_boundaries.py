import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    IdempotencyKey,
    Item,
    ItemBarcode,
    ItemUnitBinding,
    ItemUnitRevision,
    Outbox,
    UnitOfMeasure,
)
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_unit_revision_contracts_and_ownership_fail_atomically(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    path = root + f"/items/{ids['item']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None
            unit_id = item.base_unit_id
            audit_before = await db.scalar(select(func.count(Outbox.id)))
            receipts_before = await db.scalar(select(func.count(IdempotencyKey.id)))
            count = UnitOfMeasure(
                tenant_id=tenant_a,
                company_id=company,
                code="OTHER_COUNT",
                symbol="oc",
                name="Other count",
                dimension="COUNT",
                decimal_places=4,
                quantity_increment="0.0001",
            )
            mass = UnitOfMeasure(
                tenant_id=tenant_a,
                company_id=company,
                code="MASS",
                symbol="kg",
                name="Mass",
                dimension="MASS",
                decimal_places=4,
                quantity_increment="0.0001",
            )
            sibling = Item(
                tenant_id=tenant_a,
                company_id=company,
                family_id=item.family_id,
                sku="SIBLING",
                name="Sibling",
                base_unit_id=unit_id,
                sellable=True,
                purchasable=True,
                status="DRAFT",
            )
            db.add_all([count, mass, sibling])
            await db.flush()
            count_id, mass_id, sibling_id = count.id, mass.id, sibling.id
            binding = ItemUnitBinding(
                tenant_id=tenant_a,
                company_id=company,
                item_id=sibling.id,
                unit_id=unit_id,
                code="BASE",
                usage_role="BASE",
            )
            db.add(binding)
            await db.flush()
            other_binding = binding.id
            other_revision = ItemUnitRevision(
                tenant_id=tenant_a,
                company_id=company,
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
            db.add(other_revision)
            await db.flush()
            other_revision_id = other_revision.id
    body: dict[str, Any] = {
        "expected_version": 1,
        "code": "ANOTHER",
        "unit_id": str(unit_id),
        "role": "SALE",
        "numerator": 1,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "1",
        "valid_from": "2091-01-01",
    }
    for overrides, status, message in (
        ({"quantity_decimal_places": 1}, 422, "precision"),
        ({"unit_id": str(count_id), "quantity_decimal_places": 1}, 422, "fractional"),
        ({"numerator": None}, 422, "numerator"),
        ({"secondary_unit_id": str(unit_id)}, 422, "numerator"),
        ({"nominal_ratio": "1"}, 422, "numerator"),
        ({"unit_id": str(mass_id)}, 422, "dimensions"),
        ({"numerator": 2}, 422, "identity"),
        ({"role": "BASE", "unit_id": str(count_id)}, 422, "base binding"),
        ({"role": "MEASURED"}, 422, "measured conversion"),
        ({"role": "BASE"}, 409, "already has"),
        ({"valid_from": "2089-01-01"}, 409, "effective base"),
    ):
        response = await client.post(
            path + "/unit-bindings", headers=command_headers(auth), json={**body, **overrides}
        )
        assert response.status_code == status and message in response.text, response.text
    measured = {
        **body,
        "role": "MEASURED",
        "conversion_mode": "MEASURED",
        "numerator": None,
        "denominator": None,
        "secondary_unit_id": str(unit_id),
        "nominal_ratio": "1",
    }
    for overrides, message in (
        ({"role": "SALE"}, "goods measured"),
        ({"numerator": 1}, "goods measured"),
        ({"secondary_unit_id": str(count_id)}, "actual base"),
        ({"nominal_ratio": None}, "actual base"),
        ({"nominal_ratio": "0"}, "actual base"),
    ):
        response = await client.post(
            path + "/unit-bindings", headers=command_headers(auth), json={**measured, **overrides}
        )
        assert response.status_code == 422 and message in response.text, response.text
    revision = {**body, "code": "BASE", "role": "BASE", "binding_id": str(ids["item_unit_binding"])}
    for overrides, status in (
        ({"code": "CHANGED"}, 409),
        ({"binding_id": str(other_binding)}, 403),
        ({"valid_from": "2090-01-01"}, 409),
    ):
        response = await client.post(
            path + "/unit-revisions", headers=command_headers(auth), json={**revision, **overrides}
        )
        assert response.status_code == status, response.text
    for persisted, incoming in (
        ({"revision": 2147483647}, "2091-01-01"),
        ({"valid_from": dt.date(2000, 1, 1)}, "2001-01-01"),
    ):
        async with changed(
            factory, tenant_a, ItemUnitRevision, ids["item_unit_revision"], **persisted
        ):
            response = await client.post(
                path + "/unit-revisions",
                headers=command_headers(auth),
                json={**revision, "valid_from": incoming},
            )
            assert response.status_code == 409, response.text
    wrong_barcode = await client.post(
        path + "/barcodes",
        headers=command_headers(auth),
        json={"expected_version": 1, "binding_id": str(other_binding), "value": "OTHER"},
    )
    assert wrong_barcode.status_code == 403, wrong_barcode.text
    wrong_quantity = await client.post(
        path + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [{"unit_revision_id": str(other_revision_id), "quantity": "1"}],
        },
    )
    assert wrong_quantity.status_code == 403, wrong_quantity.text
    wrong_state = await client.post(
        root + f"/items/{sibling_id}/barcode-state",
        headers=command_headers(auth),
        json={"expected_version": 1, "barcode_id": str(ids["item_barcode"]), "is_active": False},
    )
    assert wrong_state.status_code == 403, wrong_state.text
    wrong_detail = await client.get(
        root + f"/items/{sibling_id}/barcodes/{ids['item_barcode']}", headers=auth
    )
    assert wrong_detail.status_code == 403, wrong_detail.text
    async with changed(factory, tenant_a, ItemBarcode, ids["item_barcode"], row_version=2147483647):
        response = await client.post(
            path + "/barcode-state",
            headers=command_headers(auth),
            json={
                "expected_version": 1,
                "barcode_id": str(ids["item_barcode"]),
                "is_active": False,
            },
        )
        assert response.status_code == 409, response.text
    duplicate = await client.post(
        path + "/barcodes",
        headers=command_headers(auth),
        json={"expected_version": 1, "value": "000abc"},
    )
    assert duplicate.status_code == 409, duplicate.text
    current = await client.get(path, headers=auth)
    assert current.json()["row_version"] == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == audit_before
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == receipts_before
    noop = await client.post(
        path + "/barcode-state",
        headers=command_headers(auth),
        json={"expected_version": 1, "barcode_id": str(ids["item_barcode"]), "is_active": True},
    )
    assert noop.status_code == 200, noop.text
    detail = await client.get(path + f"/barcodes/{ids['item_barcode']}", headers=auth)
    assert detail.json()["row_version"] == 1
    stale = await client.post(
        path + "/barcodes",
        headers=command_headers(auth),
        json={"expected_version": 1, "value": "STALE"},
    )
    assert stale.status_code == 409 and "product version changed" in stale.text, stale.text


async def test_quantity_dates_and_minimum_are_authoritative(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    path = f"/v1/companies/{company}/items/{ids['item']}"
    body = {
        "as_of": "2090-01-01",
        "components": [{"unit_revision_id": str(ids["item_unit_revision"]), "quantity": "1"}],
    }
    async with changed(factory, tenant_a, Item, ids["item"], min_sale_quantity="2"):
        response = await client.post(path + "/quantity-preview", headers=auth, json=body)
        assert response.status_code == 422 and "minimum sale" in response.text, response.text
    async with changed(
        factory,
        tenant_a,
        ItemUnitRevision,
        ids["item_unit_revision"],
        valid_to=dt.date(2090, 12, 31),
    ):
        response = await client.post(
            path + "/quantity-preview", headers=auth, json={**body, "as_of": "2091-01-01"}
        )
        assert response.status_code == 409, response.text
