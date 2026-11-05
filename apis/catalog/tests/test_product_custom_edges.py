"""Product custom-field regression coverage."""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.tax_factories import seed_tax
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_product_custom_fields import custom_facts, install
from tests.test_scheme_governance import clock

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_activation_commit_rejects_missing_required_custom_value(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await install(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        [
            {
                "validation": {"required": True},
            }
        ],
        version=50,
    )
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 200, preview.text
    payload = {
        key: preview.json()[key]
        for key in (
            "as_of",
            "expected_version",
            "expected_family_version",
            "preview_token",
        )
    }
    result = await client.post(route + "/activate", headers=command_headers(auth), json=payload)
    assert result.status_code == 409, result.text


async def test_native_decimal_condition_enforces_requiredness(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "validation": {"required": True},
                "visibility": {"field": "min_sale_quantity", "cmp": "gte", "value": "1"},
            }
        ],
    )
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 422, result.text


@pytest.mark.parametrize("kind,value", [("select", "red"), ("multi_select", ["red"])])
async def test_unchanged_retired_choice_survives_form_save(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
    value: Any,
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    definition: dict[str, Any] = {
        "data_type": kind,
        "options": {"choices": [{"value": "red", "label": "Red", "is_active": True}]},
    }
    await install(factory, tenant_a, company, user, [definition])
    body["default_item"]["custom_fields"] = {"cf_note": value}
    root = f"/v1/companies/{company}"
    created = await client.post(
        root + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    definition["options"]["choices"][0]["is_active"] = False
    await install(factory, tenant_a, company, user, [definition], version=4)
    result = await client.patch(
        root + "/items/" + created.json()["default_item"]["id"],
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "name": "New description",
            "custom_fields": {"cf_note": value},
        },
    )
    assert result.status_code == 200, result.text


async def test_create_only_actor_gets_writable_custom_fields(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "item.create",
            "item.read",
            "unit.read",
            "product_type.read",
            "brand.read",
            "brand_series.read",
        ],
    )
    body["default_item"]["custom_fields"] = {"cf_note": "permitted create"}
    root = f"/v1/companies/{company}"
    result = await client.post(root + "/product-families", headers=command_headers(auth), json=body)
    assert result.status_code == 201, result.text
    metadata = await client.get(root + "/entities/catalog.item/field-set", headers=auth)
    assert metadata.status_code == 200, metadata.text
    field = next(row for row in metadata.json()["fields"] if row["key"] == "cf_note")
    assert field["writable"] is True, field


async def test_old_optional_layout_cannot_weaken_new_required_definition(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    facts = list(custom_facts(company, user, [{"validation": {"required": True}}]))
    definition = next(row for row in facts if row.kind == "custom_definition")
    layout = next(row for row in all_facts(company, user) if row.kind == "field_config")
    facts.append(
        SnapshotRecord(
            kind="field_config",
            id=uuid7(),
            data={
                **layout.data,
                "definition_id": str(definition.id),
                "is_required": False,
            },
        )
    )
    await setup_source(factory, tenant_a, company, user, facts=tuple(facts), version=3)
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code != 201, result.text
