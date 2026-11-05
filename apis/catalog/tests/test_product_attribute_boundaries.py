import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    AttributeDefinition,
    AttributeSetMember,
    AttributeSetRevision,
    Item,
    ProductTypeRevision,
)
from tests.attribute_factories import seed_attributes
from tests.product_review_factories import changed
from tests.test_commercial_api import command_headers
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_family_attributes_enforce_type_template_axes_and_default_identity(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    family_id = product["family"]["id"]
    item_id = uuid.UUID(product["default_item"]["id"])
    revision_id = uuid.UUID(product["family"]["product_type_revision_id"])
    root = f"/v1/companies/{company}"
    path = root + f"/product-families/{family_id}/attributes"
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
    body: dict[str, Any] = {
        "expected_version": 1,
        "attributes": [declaration],
        "expected_default_item_version": 1,
        "default_item_attributes": [selected],
    }
    for entries, message in (
        ([declaration, declaration], "unique"),
        (
            [
                {
                    **declaration,
                    "definition_id": str(uuid7()),
                    "position": i,
                    "is_axis": False,
                    "options": [str(uuid7()) for _ in range(128)],
                }
                for i in range(9)
            ],
            "option bound",
        ),
        (
            [{**declaration, "definition_id": str(uuid7()), "position": i} for i in range(9)],
            "axis bound",
        ),
        ([{**declaration, "is_required": False}], "eligible required"),
        ([{**declaration, "options": []}], "eligible required"),
        ([{**declaration, "options": [str(ids["attribute_option"])] * 2}], "distinct"),
    ):
        response = await client.put(
            path, headers=command_headers(auth), json={**body, "attributes": entries}
        )
        assert response.status_code == 422 and message in response.text, response.text
    for model, key, values, message in (
        (ProductTypeRevision, revision_id, {"allow_variants": False}, "axis bound"),
        (
            AttributeDefinition,
            ids["attribute_definition"],
            {"is_variant_capable": False},
            "eligible required",
        ),
        (Item, item_id, {"default_slot": None}, "no default SKU"),
        (Item, item_id, {"row_version": 2147483647}, "default SKU version"),
    ):
        async with changed(factory, tenant_a, model, key, **values):
            response = await client.put(path, headers=command_headers(auth), json=body)
            assert response.status_code in {409, 422} and message in response.text, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, revision_id)
            template = await db.get(AttributeSetRevision, ids["attribute_set_revision"])
            assert revision is not None and template is not None
            template.published_at = utcnow()
            revision.attribute_set_revision_id = template.id
    omitted = await client.put(
        path,
        headers=command_headers(auth),
        json={**body, "attributes": [], "default_item_attributes": []},
    )
    assert omitted.status_code == 422 and "omit required" in omitted.text, omitted.text
    async with changed(
        factory, tenant_a, AttributeSetMember, ids["attribute_set_member"], allow_variant_axis=False
    ):
        forbidden = await client.put(path, headers=command_headers(auth), json=body)
        assert (
            forbidden.status_code == 422 and "exceed the pinned" in forbidden.text
        ), forbidden.text
    # A template member may be a required native scalar without becoming a variant axis.
    scalar = {
        "definition_id": str(ids["attribute_definition"]),
        "value_type": "TEXT",
        "value_text": "Blue text",
    }
    configured = await client.put(
        path,
        headers=command_headers(auth),
        json={
            **body,
            "attributes": [{**declaration, "is_axis": False, "options": []}],
            "expected_default_item_version": 1,
            "default_item_attributes": [scalar],
        },
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["family_version"] == 2
    item_path = root + f"/items/{item_id}/attributes"
    for invalid in (
        [selected, selected],
        [{**selected, "value_text": "Mixed"}],
        [{**scalar, "value_text": None}],
        [{**scalar, "definition_id": str(uuid7())}],
    ):
        response = await client.put(
            item_path,
            headers=command_headers(auth),
            json={"expected_version": 2, "attributes": invalid},
        )
        assert response.status_code == 422, response.text
    variant = await client.post(
        root + f"/product-families/{family_id}/variants",
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "item": {
                "sku": "INVALID",
                "name": "Invalid",
                "base_unit_id": product["default_item"]["base_unit_id"],
            },
            "attributes": [selected],
        },
    )
    assert variant.status_code == 409 and "declare family axes" in variant.text, variant.text
    omitted = await client.put(
        item_path, headers=command_headers(auth), json={"expected_version": 2, "attributes": []}
    )
    assert omitted.status_code == 200, omitted.text
    missing = await client.get(
        root + f"/items/{item_id}/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert missing.status_code == 200, missing.text
    assert "attribute:" + str(ids["attribute_definition"]) in missing.json()["missing"]


async def test_empty_pinned_template_does_not_allow_arbitrary_family_attributes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from sqlalchemy import delete

    company, _, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(product["family"]["product_type_revision_id"])
            )
            template = await db.get(AttributeSetRevision, ids["attribute_set_revision"])
            assert revision and template
            await db.execute(
                delete(AttributeSetMember).where(AttributeSetMember.revision_id == template.id)
            )
            template.published_at = utcnow()
            revision.attribute_set_revision_id = template.id
    response = await client.put(
        f"/v1/companies/{company}/product-families/{product['family']['id']}/attributes",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "attributes": [{"definition_id": str(ids["attribute_definition"]), "position": 0}],
        },
    )
    assert response.status_code == 422 and "pinned" in response.text, response.text
