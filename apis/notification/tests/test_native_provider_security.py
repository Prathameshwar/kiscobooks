from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import ProviderAccount, ProviderEvent
from notification.providers.sns import verify_sns
from tests.sns_fixture import TOPIC, envelope


@pytest.mark.asyncio
async def test_meta_native_signature_and_challenge_are_owner_bound(
    client: httpx.AsyncClient,
    app: Any,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret, callback = "test-provider-verification", "w" * 43
    monkeypatch.setenv("VERIFY", secret)
    with tenant_scope(tenant_a):
        session.add(
            ProviderAccount(
                tenant_id=tenant_a,
                key="meta",
                channel="whatsapp",
                provider_key="meta",
                callback_key=callback,
                display_name="Meta",
                credential_ref="env:REVIEW",
                callback_secret_ref="env:VERIFY",
                status="active",
                capabilities={"verification_token_ref": "env:VERIFY"},
            )
        )
        await session.commit()
    path = f"/v1/callbacks/whatsapp/{callback}"
    response = await client.get(
        path, params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": secret}
    )
    assert response.status_code == 200 and response.text == "12345"
    assert (
        await client.get(
            path,
            params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "wrong"},
        )
    ).status_code == 403
    body = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {"value": {"statuses": [{"id": "wamid.test", "status": "delivered"}]}}
                    ]
                }
            ]
        }
    ).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert (
        await client.post(path, content=body, headers={"X-Provider-Signature": signature})
    ).status_code == 403
    for _ in range(2):
        assert (
            await client.post(path, content=body, headers={"X-Hub-Signature-256": signature})
        ).status_code == 202
    with tenant_scope(tenant_a):
        assert len(list(await session.scalars(select(ProviderEvent)))) == 1


@pytest.mark.asyncio
async def test_sns_certificate_url_cannot_fetch_an_arbitrary_host() -> None:
    message = json.loads(envelope(b'{"eventType":"Delivery"}'))
    message["SigningCertURL"] = "https://untrusted.invalid/certificate.pem"
    loader = AsyncMock()
    with pytest.raises(PermissionDeniedError):
        await verify_sns(
            json.dumps(message).encode(), allowed_topics=[TOPIC], load_certificate=loader
        )
    loader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [("Timestamp", []), ("SigningCertURL", {}), ("Type", []), ("MessageId", "x" * 256)],
)
async def test_malformed_sns_types_fail_before_network(field, value):
    message = json.loads(envelope(b"{}"))
    message[field] = value
    loader = AsyncMock()
    with pytest.raises(PermissionDeniedError):
        await verify_sns(
            json.dumps(message).encode(), allowed_topics=[TOPIC], load_certificate=loader
        )
    loader.assert_not_called()
    with pytest.raises(PermissionDeniedError):
        await verify_sns(envelope(b"{}"), allowed_topics=[], load_certificate=loader)
    loader.assert_not_called()
