import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily, ProductTypeRevision
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_denied_dependency_fields_protect_calculation_history_and_editing(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    user = ids["actor_user"]
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    base = f"/v1/companies/{company}"
    sku = base + f"/items/{ids['item']}"
    family = base + f"/product-families/{ids['product_family']}"
    scope = base + f"/product-configuration-scopes/{ids['product_configuration_scope']}"
    config = base + "/product-configuration/effective"
    dated = {"as_of": "2090-01-01"}
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.get(Item, ids["item"])
            owner = await db.get(ProductFamily, ids["product_family"])
            assert item is not None and owner is not None
            unit_id = str(item.base_unit_id)
            revision = await db.get(ProductTypeRevision, owner.product_type_revision_id)
            assert revision is not None
            type_id = str(revision.product_type_id)
    binding = {
        "expected_version": 1,
        "code": "NEW",
        "role": "BASE",
        "unit_id": unit_id,
        "numerator": 1,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "1",
        "valid_from": "2091-01-01",
    }
    quantity = {
        **dated,
        "components": [{"unit_revision_id": str(ids["item_unit_revision"]), "quantity": "1"}],
    }
    declarations = {
        "expected_version": 1,
        "attributes": [
            {
                "definition_id": str(ids["attribute_definition"]),
                "is_axis": True,
                "is_required": True,
                "position": 0,
                "options": [str(ids["attribute_option"])],
            }
        ],
        "expected_default_item_version": 1,
        "default_item_attributes": [
            {
                "definition_id": str(ids["attribute_definition"]),
                "option_id": str(ids["attribute_option"]),
                "value_type": "TEXT",
            }
        ],
    }
    cases: list[tuple[str, str, str, str, dict[str, Any]]] = [
        ("family_group_assignment", "valid_to", "GET", sku + "/requirements", dated),
        ("product_configuration_adoption", "effective_on", "GET", sku + "/configuration", dated),
        ("item_barcode", "value", "GET", sku + "/requirements", dated),
        ("family_attribute", "position", "PUT", family + "/attributes", declarations),
        ("item_attribute_value", "value_type", "PUT", family + "/attributes", declarations),
        ("item_unit_revision", "valid_to", "POST", sku + "/unit-bindings", binding),
        ("item_unit_binding", "code", "POST", sku + "/quantity-preview", quantity),
        ("item_unit_binding", "code", "POST", sku + "/unit-bindings", binding),
        ("product_entry_option_policy", "revision_id", "GET", config, {**dated, "kind": "GOODS"}),
        (
            "product_entry_option_policy",
            "draft_id",
            "GET",
            base + f"/product-configurations/{ids['product_configuration_draft']}",
            {},
        ),
        (
            "product_configuration_revision",
            "effective_from",
            "GET",
            scope + "/revisions",
            {"effective_on": "2090-01-01"},
        ),
        ("product_configuration_revision", "scope_id", "GET", scope + "/revisions", {}),
        (
            "family_manufacturer",
            "valid_to",
            "POST",
            family + "/manufacturers",
            {
                "expected_version": 1,
                "manufacturer_id": str(ids["manufacturer"]),
                "role": "IMPORTER",
                "valid_from": "2090-01-01",
            },
        ),
        (
            "item_barcode",
            "value",
            "POST",
            sku + "/barcode-state",
            {"expected_version": 1, "barcode_id": str(ids["item_barcode"]), "is_active": False},
        ),
        ("family_category", "family_id", "GET", family + "/categories", {}),
        ("family_group_assignment", "valid_from", "GET", family + "/groups", dated),
        (
            "item_group_parent",
            "valid_from",
            "GET",
            config,
            {**dated, "kind": "GOODS", "group_id": str(ids["item_group"])},
        ),
        (
            "product_type_revision",
            "allow_variants",
            "GET",
            config,
            {**dated, "kind": "GOODS", "product_type_id": type_id},
        ),
        (
            "family_group_assignment",
            "valid_to",
            "POST",
            family + "/groups",
            {"expected_version": 1, "group_id": str(ids["item_group"]), "valid_from": "2091-01-01"},
        ),
    ]
    for version, (entity, field, method, path, body) in enumerate(cases, 3):
        await policy(
            factory, tenant_a, company, user, "catalog." + entity, field, "read", version=version
        )
        if method == "GET":
            response = await client.get(path, headers=auth, params=body)
        else:
            response = await client.request(method, path, headers=command_headers(auth), json=body)
        assert response.status_code == 403, (entity, field, response.text)
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.get(Item, ids["item"])
            owner = await db.get(ProductFamily, ids["product_family"])
            assert item is not None and owner is not None
            assert item.row_version == owner.row_version == 1
