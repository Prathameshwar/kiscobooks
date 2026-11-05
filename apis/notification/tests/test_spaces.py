from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.tenant_context import TenantContextError
from billing_platform.ids import uuid7
from sqlalchemy import select

from notification.models import ProviderAccount
from notification.ownership import session_factory, space_scope
from tests.api_support import ACTOR_SECRET, actor_headers


def provider(tenant, space, key):
    return ProviderAccount(
        id=uuid7(),
        tenant_id=tenant,
        space_id=space,
        key=key,
        callback_key=str(uuid7()),
        channel="email",
        provider_key="ses",
        display_name=key,
        credential_ref="env:TEST",
        status="pending",
    )


async def test_same_tenant_spaces_and_cached_lookup_are_isolated(engine, tenant_a):
    platform = uuid7()
    factory = session_factory(engine)
    async with factory() as db:
        with unfiltered():
            own, foreign = (
                provider(tenant_a, tenant_a, "same"),
                provider(tenant_a, platform, "same"),
            )
            db.add_all([own, foreign])
            await db.commit()
        with tenant_scope(tenant_a):
            assert await db.get(ProviderAccount, foreign.id) is None
            assert [r.id for r in await db.scalars(select(ProviderAccount))] == [own.id]
        with tenant_scope(tenant_a), space_scope(platform):
            with pytest.raises(TenantContextError, match="change partition"):
                await db.get(ProviderAccount, foreign.id)
    async with factory() as db:
        with tenant_scope(tenant_a), space_scope(platform):
            assert [r.id for r in await db.scalars(select(ProviderAccount))] == [foreign.id]


async def test_partition_write_and_ownership_change_are_rejected(engine, tenant_a):
    factory = session_factory(engine)
    async with factory() as db:
        with tenant_scope(tenant_a):
            db.add(provider(tenant_a, uuid7(), "wrong"))
            with pytest.raises(TenantContextError, match="outside"):
                await db.flush()
            await db.rollback()
            row = provider(tenant_a, tenant_a, "own")
            db.add(row)
            await db.commit()
            row.space_id = uuid7()
            with pytest.raises(TenantContextError):
                await db.flush()


def platform_headers(tenant, permissions):
    result = actor_headers(tenant_id=tenant, user_id=uuid7(), permissions=permissions)
    body = json.loads(base64.urlsafe_b64decode(result["X-Actor-Context"] + "=="))
    body["user_type"] = "platform_notification_operator"
    body["notification_authority"] = {"path": "/v1/platform/provider-accounts", "method": "GET"}
    raw = json.dumps(body).encode()
    return {
        "X-Actor-Context": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
        "X-Actor-Signature": hmac.new(ACTOR_SECRET.encode(), raw, hashlib.sha256).hexdigest(),
    }


async def test_platform_requires_marker_owner_and_separate_permissions(client, app, tenant_a):
    settings = app.state.settings
    settings.platform_owner_tenant_id = tenant_a
    settings.platform_space_id = uuid7()
    assert (await client.get("/v1/provider-accounts")).status_code == 401
    path = "/v1/platform/provider-accounts"
    tenant = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["platform.notification_provider.read"]
    )
    assert (await client.get(path, headers=tenant)).status_code == 403
    assert (
        await client.get(path, headers=platform_headers(tenant_a, ["notification.provider.read"]))
    ).status_code == 403
    proof = platform_headers(tenant_a, ["platform.notification_provider.read"])
    assert (await client.get(path, headers=proof)).status_code == 200
    assert (await client.get("/v1/provider-accounts", headers=proof)).status_code == 403
