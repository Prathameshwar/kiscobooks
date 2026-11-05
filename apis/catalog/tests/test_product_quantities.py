import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import PackType, UnitOfMeasure
from tests.test_commercial_api import command_headers
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_alternate_and_measured_entries_obey_sku_base_grid(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    item = product["default_item"]
    root = f"/v1/companies/{company}"
    path = root + f"/items/{item['id']}"
    updated = await client.patch(
        path, headers=command_headers(auth), json={"expected_version": 1, "min_sale_quantity": "2"}
    )
    assert updated.status_code == 200, updated.text
    base = {
        "expected_version": 2,
        "code": "BASE",
        "unit_id": item["base_unit_id"],
        "role": "BASE",
        "numerator": 1,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "2",
        "valid_from": "2090-01-01",
    }
    created = await client.post(path + "/unit-bindings", headers=command_headers(auth), json=base)
    assert created.status_code == 200, created.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            pair = UnitOfMeasure(
                tenant_id=tenant_a,
                company_id=company,
                code="PAIR",
                symbol="pr",
                name="Pair",
                dimension="COUNT",
                decimal_places=0,
                quantity_increment="1",
            )
            box = PackType(tenant_id=tenant_a, company_id=company, code="BOX", name="Box")
            db.add_all([pair, box])
            await db.flush()
            pair_id, pack_id = str(pair.id), str(box.id)
    alternate = {
        **base,
        "expected_version": 3,
        "code": "PAIR",
        "unit_id": pair_id,
        "role": "PACK",
        "pack_type_id": pack_id,
        "quantity_increment": "1",
    }
    incompatible = await client.post(
        path + "/unit-bindings", headers=command_headers(auth), json=alternate
    )
    assert incompatible.status_code == 422, incompatible.text
    created = await client.post(
        path + "/unit-bindings", headers=command_headers(auth), json={**alternate, "numerator": 2}
    )
    assert created.status_code == 200, created.text
    measured = {
        **alternate,
        "expected_version": 4,
        "code": "MEASURED",
        "role": "MEASURED",
        "conversion_mode": "MEASURED",
        "numerator": None,
        "denominator": None,
        "secondary_unit_id": item["base_unit_id"],
        "nominal_ratio": "2",
    }
    created = await client.post(
        path + "/unit-bindings", headers=command_headers(auth), json=measured
    )
    assert created.status_code == 200, created.text
    bindings = await client.get(path + "/unit-bindings", headers=auth)
    records = {row["code"]: row for row in bindings.json()["items"]}
    revisions = {}
    for code, binding in records.items():
        page = await client.get(
            root + f"/item-unit-bindings/{binding['id']}/revisions", headers=auth
        )
        assert page.status_code == 200, page.text
        revisions[code] = page.json()["items"][0]["id"]
    component = {"unit_revision_id": revisions["MEASURED"], "quantity": "1"}
    for actual in (None, "0", "3"):
        invalid = await client.post(
            path + "/quantity-preview",
            headers=auth,
            json={
                "as_of": "2090-01-01",
                "components": [{**component, "measured_base_quantity": actual}],
            },
        )
        assert invalid.status_code == 422, invalid.text
    valid = await client.post(
        path + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [
                {**component, "measured_base_quantity": "6"},
                {"unit_revision_id": revisions["PAIR"], "quantity": "2"},
            ],
        },
    )
    assert valid.status_code == 200, valid.text
    assert Decimal(valid.json()["base_quantity"]) == Decimal("10")
    incompatible_revision = await client.post(
        path + "/unit-revisions",
        headers=command_headers(auth),
        json={
            **base,
            "binding_id": records["BASE"]["id"],
            "expected_version": 5,
            "quantity_increment": "3",
            "valid_from": "2091-01-01",
        },
    )
    assert incompatible_revision.status_code == 422, incompatible_revision.text
    current = await client.get(path, headers=auth)
    assert current.json()["row_version"] == 5
    compatible_revision = await client.post(
        path + "/unit-revisions",
        headers=command_headers(auth),
        json={
            **base,
            "binding_id": records["BASE"]["id"],
            "expected_version": 5,
            "quantity_increment": "1",
            "valid_from": "2091-01-01",
        },
    )
    assert compatible_revision.status_code == 200, compatible_revision.text
    frozen_pack = await client.patch(
        root + f"/pack-types/{pack_id}",
        headers=command_headers(auth),
        json={"expected_version": 1, "code": "REPLACED"},
    )
    assert (
        frozen_pack.status_code == 409 and "referenced by product definitions" in frozen_pack.text
    ), frozen_pack.text
