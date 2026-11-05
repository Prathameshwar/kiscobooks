import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductConfigurationRevision, ProductEntryOptionPolicy
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_disabled_choices_block_authoring_and_report_existing_incompatibilities(
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
    family = root + f"/product-families/{ids['product_family']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductConfigurationRevision, ids["product_configuration_revision"]
            )
            options = await db.get(ProductEntryOptionPolicy, ids["product_entry_option_policy"])
            item = await db.get(Item, ids["item"])
            assert revision is not None and options is not None and item is not None
            unit_id = str(item.base_unit_id)
            revision.effective_from = dt.date(2000, 1, 1)
            for option in (
                "variants",
                "category",
                "manufacturer",
                "barcode",
                "alternate_units",
                "compound_units",
                "measured_units",
            ):
                setattr(options, option + "_mode", "DISABLED")
    selected = {
        "definition_id": str(ids["attribute_definition"]),
        "option_id": str(ids["attribute_option"]),
        "value_type": "TEXT",
    }
    binding = {
        "expected_version": 1,
        "code": "PACK",
        "unit_id": unit_id,
        "role": "PACK",
        "numerator": 1,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "1",
        "valid_from": "2091-01-01",
    }
    for method, route, body in (
        ("POST", path + "/barcodes", {"expected_version": 1, "value": "NEW"}),
        (
            "PUT",
            family + "/categories",
            {
                "expected_version": 1,
                "categories": [
                    {
                        "scheme_id": str(ids["category_scheme"]),
                        "category_id": str(ids["item_category"]),
                    }
                ],
            },
        ),
        (
            "POST",
            family + "/manufacturers",
            {
                "expected_version": 1,
                "manufacturer_id": str(ids["manufacturer"]),
                "valid_from": "2091-01-01",
            },
        ),
        ("POST", path + "/unit-bindings", binding),
        (
            "POST",
            path + "/unit-bindings",
            {
                **binding,
                "role": "MEASURED",
                "conversion_mode": "MEASURED",
                "numerator": None,
                "denominator": None,
                "secondary_unit_id": unit_id,
                "nominal_ratio": "1",
            },
        ),
        (
            "POST",
            family + "/variants",
            {
                "expected_version": 1,
                "item": {"sku": "NEW", "name": "New", "base_unit_id": unit_id},
                "attributes": [selected],
            },
        ),
    ):
        response = await client.request(method, route, headers=command_headers(auth), json=body)
        assert (
            response.status_code == 422 and "disables this native choice" in response.text
        ), response.text
    quantity = await client.post(
        path + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [{"unit_revision_id": str(ids["item_unit_revision"]), "quantity": "1"}]
            * 2,
        },
    )
    assert quantity.status_code == 422 and "compound quantity entry" in quantity.text, quantity.text
    ready = await client.get(path + "/requirements", headers=auth, params={"as_of": "2090-01-01"})
    assert ready.status_code == 200, ready.text
    assert {
        "forbidden_variants",
        "forbidden_category",
        "forbidden_manufacturer",
        "forbidden_barcode",
    } <= set(ready.json()["missing"])
    async with changed(
        factory,
        tenant_a,
        ProductEntryOptionPolicy,
        ids["product_entry_option_policy"],
        barcode_mode="REQUIRED",
        alternate_units_mode="REQUIRED",
        compound_units_mode="REQUIRED",
        measured_units_mode="REQUIRED",
    ):
        ready = await client.get(
            path + "/requirements", headers=auth, params={"as_of": "2090-01-01"}
        )
        assert ready.status_code == 200, ready.text
        assert {"alternate_units", "compound_units", "measured_units"} <= set(
            ready.json()["missing"]
        )
