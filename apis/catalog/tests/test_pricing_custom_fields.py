import uuid

import httpx
import pytest
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import create, setup_pricing
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_plan_custom_fields_are_descriptive_required_and_protected(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    company, user = uuid.UUID(root.rsplit("/", 1)[1]), ids["actor_user"]
    facts = all_facts(company, user)
    rows = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "entity_type": "catalog.price_plan",
                **({"is_required": True} if row.kind == "field_config" else {}),
            },
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in facts
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=rows)
    level = await create(client, root, auth, "/pricing/bootstrap", {})
    body = {
        "code": "SALE",
        "name": "Retail",
        "purpose": "SALE",
        "price_level_id": level["id"],
        "currency": "INR",
        "tax_basis": "EXCLUSIVE",
    }
    missing = await client.post(root + "/price-plans", headers=command_headers(auth), json=body)
    assert missing.status_code == 422, missing.text
    plan = await create(
        client, root, auth, "/price-plans", {**body, "custom_fields": {"cf_note": "Private"}}
    )
    path = root + "/price-plans/" + plan["id"]
    detail = await client.get(path, headers=auth)
    assert detail.json()["custom_fields"] == {"cf_note": "Private"}, detail.text
    edited = await client.patch(
        path,
        headers=command_headers(auth),
        json={"expected_version": 1, "name": "Sale", "custom_fields": {"cf_note": "Revised"}},
    )
    assert edited.status_code == 200, edited.text
    assert (await client.get(path, headers=auth)).json()["custom_fields"] == {"cf_note": "Revised"}
    denied = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **next(row.data for row in facts if row.kind == "field_policy"),
            "entity_type": "catalog.price_plan",
            "field_key": "custom_field:cf_note",
            "access": "read",
            "subject_type": "user",
            "subject_id": str(user),
        },
    )
    await setup_source(factory, tenant_a, company, user, version=4, facts=(*rows, denied))
    assert (await client.get(path, headers=auth)).json()["custom_fields"] == {}
    page = await client.get(root + "/price-plans", headers=auth)
    assert "custom_fields" not in page.json()["items"][0] and "Revised" not in page.text
    managing = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    metadata = await client.get(root + "/entities/catalog.price_plan/field-set", headers=managing)
    assert metadata.status_code == 200, metadata.text
    assert "custom_field:cf_note" not in {field["key"] for field in metadata.json()["fields"]}


async def test_generated_pricing_fields_are_readonly_in_authoring_metadata(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, _ = await setup_pricing(factory, tenant_a)
    for entity, generated in (
        ("item_price_draft", {"status", "item_id", "unit_revision_id", "currency"}),
        ("item_price", {"source_draft_id", "series_id", "amount"}),
        ("item_price_scope", {"subject_kind"}),
        ("item_price_series", {"item_id", "currency", "audience_kind"}),
        ("commercial_policy_scope", {"owner_id"}),
    ):
        response = await client.get(
            root + "/entities/catalog." + entity + "/field-set", headers=auth
        )
        assert response.status_code == 200, response.text
        fields = {field["key"]: field for field in response.json()["fields"]}
        assert all(not fields[key]["writable"] for key in generated), entity
