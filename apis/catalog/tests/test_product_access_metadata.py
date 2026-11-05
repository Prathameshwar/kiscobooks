import base64
import hashlib
import hmac
import json
import time
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from tests.conftest import ACTOR_SECRET
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_references import setup_owner


async def test_product_and_alias_metadata_preserve_server_owned_fields(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current, _ = await setup_product(factory, tenant_a)
    for entity, readonly in (
        ("catalog.product_family", {"status", "structure_mode", "row_version"}),
        ("catalog.item", {"status", "default_slot", "family_id", "row_version"}),
    ):
        result = await client.get(
            f"/v1/companies/{company}/entities/{entity}/field-set", headers=current
        )
        assert result.status_code == 200, result.text
        fields = {field["key"]: field for field in result.json()["fields"]}
        assert all(fields[key]["writable"] is False for key in readonly)
        assert fields["name"]["writable"] is True
    company, _, current, _, _ = await setup_owner(client, factory, tenant_a)
    result = await client.get(
        f"/v1/companies/{company}/entities/catalog.master_alias/field-set", headers=current
    )
    assert result.status_code == 200, result.text
    fields = {field["key"]: field for field in result.json()["fields"]}
    assert fields["alias"]["writable"] is True
    assert fields["canonical_value"]["writable"] is False


async def test_support_sessions_cannot_create_products(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current, body = await setup_product(factory, tenant_a)
    encoded = current["x-actor-context"]
    raw = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    raw.update(
        actor_user_id=str(uuid7()),
        impersonation_id=str(uuid7()),
        impersonation_expires_at=int(time.time()) + 300,
    )
    payload = json.dumps(raw).encode()
    support = {
        "x-actor-context": base64.urlsafe_b64encode(payload).rstrip(b"=").decode(),
        "x-actor-signature": hmac.new(ACTOR_SECRET.encode(), payload, hashlib.sha256).hexdigest(),
    }
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(support), json=body
    )
    assert result.status_code == 403, result.text


async def test_inactive_unit_cannot_gain_new_conversion(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    unit_id = uuid.UUID(body["default_item"]["base_unit_id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            unit = await db.get(UnitOfMeasure, unit_id)
            assert unit is not None
            unit.is_active = False
    current = headers(company, tenant=tenant_a, user=user, permission=["unit.read", "unit.manage"])
    result = await client.post(
        f"/v1/companies/{company}/unit-conversions",
        headers=command_headers(current),
        json={
            "from_unit_id": str(unit_id),
            "canonical_unit_id": str(unit_id),
            "numerator": 1,
            "denominator": 1,
        },
    )
    assert result.status_code == 409, result.text
