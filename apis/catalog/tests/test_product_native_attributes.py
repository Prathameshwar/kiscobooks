import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import AttributeDefinition, Item, UnitOfMeasure
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_typed_sku_values_preserve_exact_native_types_and_cannot_be_orphaned(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            unit = UnitOfMeasure(
                tenant_id=tenant_a,
                company_id=company,
                code="KG",
                name="Kilogram",
                symbol="kg",
                dimension="MASS",
                decimal_places=3,
                quantity_increment="0.001",
            )
            definitions = [
                AttributeDefinition(
                    tenant_id=tenant_a,
                    company_id=company,
                    code=kind,
                    name=kind,
                    value_type=kind,
                    is_variant_capable=False,
                    measurement_dimension="MASS" if kind == "DECIMAL" else None,
                )
                for kind in ("TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE")
            ]
            db.add_all([unit, *definitions])
            await db.flush()
            unit_id = str(unit.id)
            item = await db.get(Item, ids["item"])
            assert item is not None
            base_unit_id = str(item.base_unit_id)
            definition_ids = {row.value_type: str(row.id) for row in definitions}
    declaration = {
        "definition_id": str(ids["attribute_definition"]),
        "is_axis": True,
        "is_required": True,
        "position": 0,
        "options": [str(ids["attribute_option"])],
    }
    selected = {
        "definition_id": str(ids["attribute_definition"]),
        "option_id": str(ids["attribute_option"]),
        "value_type": "TEXT",
    }
    declarations = [declaration] + [
        {"definition_id": key, "is_required": True, "position": index}
        for index, key in enumerate(definition_ids.values(), 1)
    ]
    values: list[dict[str, Any]] = [
        selected,
        {
            "definition_id": definition_ids["TEXT"],
            "value_type": "TEXT",
            "value_text": "Specification",
        },
        {
            "definition_id": definition_ids["INTEGER"],
            "value_type": "INTEGER",
            "value_integer": "9223372036854775807",
        },
        {
            "definition_id": definition_ids["DECIMAL"],
            "value_type": "DECIMAL",
            "value_decimal": "1.250",
            "unit_id": unit_id,
        },
        {
            "definition_id": definition_ids["BOOLEAN"],
            "value_type": "BOOLEAN",
            "value_boolean": True,
        },
        {"definition_id": definition_ids["DATE"], "value_type": "DATE", "value_date": "2090-01-01"},
    ]
    family_path = base + f"/product-families/{ids['product_family']}/attributes"
    configured = await client.put(
        family_path,
        headers=command_headers(auth),
        json={
            "expected_default_item_version": 1,
            "expected_version": 1,
            "attributes": declarations,
            "default_item_attributes": values,
        },
    )
    assert configured.status_code == 200, configured.text
    item_path = base + f"/items/{ids['item']}/attributes"
    for invalid, status in (
        ({**values[3], "value_decimal": "0.0005"}, 422),
        ({**values[3], "unit_id": str(ids["item_unit_binding"])}, 404),
        ({**values[3], "unit_id": base_unit_id}, 422),
        ({**values[1], "option_id": str(ids["attribute_option"]), "value_text": None}, 403),
        ({**values[1], "value_type": "BOOLEAN", "value_text": None, "value_boolean": True}, 422),
    ):
        response = await client.put(
            item_path,
            headers=command_headers(auth),
            json={"expected_version": 2, "attributes": [selected, invalid]},
        )
        assert response.status_code == status, response.text
    orphan = await client.put(
        family_path,
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "attributes": [declaration],
            "expected_default_item_version": 1,
            "default_item_attributes": [selected],
        },
    )
    assert orphan.status_code == 409, orphan.text
    listed = await client.get(item_path, headers=auth)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 6
    for row in listed.json()["items"]:
        detail = await client.get(item_path + "/" + row["id"], headers=auth)
        assert detail.status_code == 200, detail.text
        if detail.json()["value_type"] == "INTEGER":
            assert detail.json()["value_integer"] == "9223372036854775807"
    # Draft omissions remain visible readiness requirements until explicitly filled.
    omitted = await client.put(
        item_path,
        headers=command_headers(auth),
        json={"expected_version": 2, "attributes": [selected]},
    )
    assert omitted.status_code == 200, omitted.text
    ready = await client.get(
        base + f"/items/{ids['item']}/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert ready.status_code == 200, ready.text
    assert {"attribute:" + value for value in definition_ids.values()} <= set(
        ready.json()["missing"]
    )
