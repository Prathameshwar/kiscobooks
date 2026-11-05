"""Sales-channel HTTP contract: create/read/update/activate/deactivate/list."""

import uuid

import httpx
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers


async def _auth(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
) -> dict[str, str]:
    await setup_source(factory, tenant, company, user)
    return headers(
        company,
        tenant=tenant,
        user=user,
        permission=["sales_channel.read", "sales_channel.manage"],
    )


async def test_sales_channel_full_lifecycle(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    auth = await _auth(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}/sales-channels"

    # Create
    created = await client.post(
        root, headers=command_headers(auth), json={"code": "WEB", "name": "Web store"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    channel_id = body["id"]
    assert body["code"] == "WEB"
    assert body["is_active"] is True
    assert body["row_version"] == 1

    # Read
    detail = await client.get(f"{root}/{channel_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["code"] == "WEB"

    # List
    listed = await client.get(root, headers=auth)
    assert listed.status_code == 200
    assert any(item["id"] == channel_id for item in listed.json()["items"])

    # Update name
    renamed = await client.patch(
        f"{root}/{channel_id}",
        headers=command_headers(auth),
        json={"expected_version": 1, "name": "Web storefront"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Web storefront"
    assert renamed.json()["row_version"] == 2

    # Deactivate
    off = await client.post(
        f"{root}/{channel_id}/deactivate",
        headers=command_headers(auth),
        json={"expected_version": 2},
    )
    assert off.status_code == 200, off.text
    assert off.json()["is_active"] is False

    # Activate back
    on = await client.post(
        f"{root}/{channel_id}/activate",
        headers=command_headers(auth),
        json={"expected_version": 3},
    )
    assert on.status_code == 200, on.text
    assert on.json()["is_active"] is True


async def test_sales_channel_denies_unauthenticated_and_underprivileged(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    read_only = headers(company, tenant=tenant_a, user=user, permission="sales_channel.read")
    root = f"/v1/companies/{company}/sales-channels"

    unauth = await client.get(root)
    assert unauth.status_code == 401

    forbidden = await client.post(
        root,
        headers={**read_only, "Idempotency-Key": str(uuid7())},
        json={"code": "WEB", "name": "Web"},
    )
    assert forbidden.status_code == 403


async def test_sales_channel_code_uniqueness_returns_409(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    auth = await _auth(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}/sales-channels"
    body = {"code": "STORE", "name": "In-store"}
    first = await client.post(root, headers=command_headers(auth), json=body)
    assert first.status_code == 201
    duplicate = await client.post(root, headers=command_headers(auth), json=body)
    assert duplicate.status_code == 409, duplicate.text


async def test_sales_channel_cross_tenant_404(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_a, user_a = uuid7(), uuid7()
    company_b, user_b = uuid7(), uuid7()
    auth_a = await _auth(factory, tenant_a, company_a, user_a)
    auth_b = await _auth(factory, tenant_b, company_b, user_b)
    created = await client.post(
        f"/v1/companies/{company_a}/sales-channels",
        headers=command_headers(auth_a),
        json={"code": "WEB", "name": "Web"},
    )
    assert created.status_code == 201
    channel_id = created.json()["id"]
    # Tenant B trying to read A's channel via tenant B's company scope: 404 (row not there).
    cross = await client.get(
        f"/v1/companies/{company_b}/sales-channels/{channel_id}", headers=auth_b
    )
    assert cross.status_code == 404
