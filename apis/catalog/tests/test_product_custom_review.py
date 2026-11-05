"""Additional security and cross-company checks for product field rollout."""

import base64
import hashlib
import hmac
import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import ACTOR_SECRET
from tests.product_factories import setup_product
from tests.test_commercial_api import command_headers
from tests.test_product_custom_fields import install
from tests.test_product_field_adoption import manager, review_and_adopt

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize(
    "kind,first_value,second_value", [("text", "DUPLICATE", "DUPLICATE"), ("integer", 7, "7")]
)
async def test_tenant_unique_blocks_values_from_a_company_with_an_older_contract(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
    first_value: Any,
    second_value: Any,
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    other, user2, auth2, body2 = await setup_product(factory, tenant_a)
    await install(factory, tenant_a, other, user2, [{"data_type": "text"}])
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "data_type": kind,
                "requires_adoption": True,
                "is_searchable": True,
                "validation": {"unique_within": "tenant"},
            }
        ],
    )
    admin = manager(company, tenant_a, user)
    payload = json.loads(base64.urlsafe_b64decode(admin["x-actor-context"] + "=="))
    payload["grants"][0].update(scope_type="tenant", scope_id=str(uuid.UUID(int=0)))
    raw = json.dumps(payload).encode()
    admin = {
        "x-actor-context": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
        "x-actor-signature": hmac.new(ACTOR_SECRET.encode(), raw, hashlib.sha256).hexdigest(),
    }
    root = f"/v1/companies/{company}/entities/catalog.item/custom-field-adoption"
    await review_and_adopt(client, root, admin)
    body["default_item"]["custom_fields"] = {"cf_note": first_value}
    body2["default_item"]["custom_fields"] = {"cf_note": second_value}
    first = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/v1/companies/{other}/product-families", headers=command_headers(auth2), json=body2
    )
    assert second.status_code == 409, second.text


async def test_pending_retirement_keeps_accepted_field_visible(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, _ = await setup_product(factory, tenant_a)
    definition = {"requires_adoption": True}
    await install(factory, tenant_a, company, user, [definition])
    root = f"/v1/companies/{company}/entities/catalog.item"
    await review_and_adopt(
        client, root + "/custom-field-adoption", manager(company, tenant_a, user)
    )
    await install(factory, tenant_a, company, user, [{**definition, "is_active": False}], version=4)
    response = await client.get(root + "/field-set?operation=update", headers=auth)
    assert response.status_code == 200, response.text
    field = next(field for field in response.json()["fields"] if field["key"] == "cf_note")
    assert field["custom"]["is_active"] and field["visible"]


async def test_retired_saved_value_has_readonly_product_metadata(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(factory, tenant_a, company, user, [{}])
    body["default_item"]["custom_fields"] = {"cf_note": "history"}
    base = f"/v1/companies/{company}"
    created = await client.post(
        base + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    item = created.json()["default_item"]
    await install(factory, tenant_a, company, user, [{"is_active": False}], version=4)
    response = await client.get(
        base + "/entities/catalog.item/field-set",
        headers=auth,
        params={"operation": "update", "object_id": item["id"]},
    )
    assert response.status_code == 200, response.text
    matching = [f for f in response.json()["fields"] if f["key"] == "cf_note"]
    assert len(matching) == 1 and not matching[0]["writable"]


async def test_metadata_exposes_adopted_contract_version(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, _ = await setup_product(factory, tenant_a)
    await install(factory, tenant_a, company, user, [{"requires_adoption": True}])
    root = f"/v1/companies/{company}/entities/catalog.item"
    before = await client.get(root + "/field-set", headers=auth)
    await review_and_adopt(
        client, root + "/custom-field-adoption", manager(company, tenant_a, user)
    )
    after = await client.get(root + "/field-set", headers=auth)
    assert before.status_code == after.status_code == 200
    assert after.json().get("adoption_version", 0) > before.json().get("adoption_version", 0)


async def test_preview_flags_incompatible_values_in_another_company(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, _ = await setup_product(factory, tenant_a)
    other, user2, auth2, body2 = await setup_product(factory, tenant_a)
    await install(factory, tenant_a, other, user2, [{"data_type": "text"}])
    body2["default_item"]["custom_fields"] = {"cf_note": "seven"}
    created = await client.post(
        f"/v1/companies/{other}/product-families", headers=command_headers(auth2), json=body2
    )
    assert created.status_code == 201, created.text
    await install(factory, tenant_a, other, user, [{"data_type": "text"}], version=4)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "data_type": "integer",
                "requires_adoption": True,
                "is_searchable": True,
                "validation": {"unique_within": "tenant"},
            }
        ],
    )
    auth = manager(company, tenant_a, user)
    payload = json.loads(base64.urlsafe_b64decode(auth["x-actor-context"] + "=="))
    payload["grants"][0].update(scope_type="tenant", scope_id=str(uuid.UUID(int=0)))
    raw = json.dumps(payload).encode()
    auth = {
        "x-actor-context": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
        "x-actor-signature": hmac.new(ACTOR_SECRET.encode(), raw, hashlib.sha256).hexdigest(),
    }
    preview = await client.post(
        f"/v1/companies/{company}/entities/catalog.item/custom-field-adoption/preview", headers=auth
    )
    assert preview.status_code == 200, preview.text
    assert not preview.json()["eligible"]
    assert preview.json()["issues"][0]["owner_id"] == created.json()["default_item"]["id"]
