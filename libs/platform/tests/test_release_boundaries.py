"""Shared hostile-input and delivery boundaries used by the Catalog release."""

import base64
import datetime as dt
import json
import os
from dataclasses import replace

import httpx
import pytest
from joserfc.jwk import RSAKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.bulk import BulkTarget
from billing_platform.delivery import publish_batch
from billing_platform.errors import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.oidc import (
    AccessTokenVerifier,
    IdentityProviderUnavailableError,
    _header,
)
from billing_platform.pagination import CursorCodec
from billing_platform.publisher import PublisherConfig
from billing_platform.service_auth import ServiceKey
from billing_platform.webhooks import TimestampedHmacVerifier
from tests.test_oidc import config


def test_invalid_scope_lifetimes_and_staged_target_shapes_are_rejected() -> None:
    for changes in (
        {"audience": ""},
        {"api_scope": "one two"},
        {"cache_seconds": 4},
        {"max_token_seconds": 901},
    ):
        with pytest.raises(ValueError):
            replace(config(), **changes)
    for value in ({"record": "new", "code": "EXISTING"}, {"field": "family.id"}):
        with pytest.raises(ValueError):
            BulkTarget.model_validate(value)
    for values in ({"context": ""}, {"context": "job", "ttl_seconds": 0}):
        with pytest.raises(ValueError):
            CursorCodec(os.urandom(32), **values)
    verifier = TimestampedHmacVerifier(os.urandom(32), clock=lambda: 100)
    with pytest.raises(ValidationFailedError):
        verifier.verify(b"body", timestamp="not-a-time", signature="invalid")
    with pytest.raises(PermissionDeniedError):
        verifier.verify(b"body", timestamp="100", signature="invalid")
    header: object
    for header in (
        [],
        {"alg": "HS256", "kid": "x"},
        {"alg": "RS256", "kid": "x", "jku": "https://other.test"},
    ):
        encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        with pytest.raises(ValueError):
            _header(encoded + ".body.signature")


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"keys": []},
        {"keys": [{"kty": "RSA", "kid": None}]},
        {"keys": [{"kty": "RSA", "kid": "x", "d": "private"}]},
    ],
)
async def test_malformed_public_key_documents_fail_closed(document: object) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=document))
    ) as client:
        with pytest.raises(IdentityProviderUnavailableError):
            await AccessTokenVerifier(config(), client)._keys("x")


async def test_oversized_keys_and_unknown_key_retry_are_bounded() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 131073))
    ) as client:
        with pytest.raises(IdentityProviderUnavailableError):
            await AccessTokenVerifier(config(), client)._keys("x")
    key = RSAKey.generate_key(2048, {"kid": "known"})
    requests = 0

    def response(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={"keys": [key.as_dict()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        verifier = AccessTokenVerifier(config(), client)
        for _ in range(2):
            with pytest.raises(AuthenticationRequiredError):
                await verifier._keys("unknown")
        assert requests == 1


async def test_delivery_and_supervisor_reject_unbounded_retries_or_naive_cutoffs(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async def unreachable(*args: object) -> bool:
        raise AssertionError("invalid configuration reached transport")

    key = ServiceKey("catalog", "audit", frozenset({"catalog.bulk_job.update"}), os.urandom(32))
    settings = PublisherConfig(
        database_url="sqlite+aiosqlite:///:memory:",
        broker_url="amqp://test.invalid",
        broker_user="test",
        key=key,
        key_id="current",
        exchange="platform.audit",
    )
    for changes in ({"maximum_attempts": 0}, {"occurred_after": dt.datetime(2026, 1, 1)}):
        with pytest.raises(ValueError):
            replace(settings, **changes)
        with pytest.raises(ValueError):
            await publish_batch(factory, unreachable, **changes)
