from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.pagination import CursorCodec, cursor_context


def test_signed_non_object_is_a_validation_error() -> None:
    key = secrets.token_bytes(32)
    body = json.dumps([]).encode()
    token = (
        base64.urlsafe_b64encode(body + hmac.digest(key, body, hashlib.sha256))
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(ValidationFailedError):
        CursorCodec(key, context="products").decode(token)


def test_noncanonical_base64_is_rejected() -> None:
    codec = CursorCodec(secrets.token_bytes(32), context="products")
    token = codec.encode({"id": "7"})
    with pytest.raises(ValidationFailedError):
        codec.decode("!" + token)


def test_expiry_future_issuance_and_rotation() -> None:
    old, new = secrets.token_bytes(32), secrets.token_bytes(32)
    token = CursorCodec(old, context="p", key_id="old", clock=lambda: 100).encode({"id": "7"})
    rotated = CursorCodec(new, context="p", verification_keys={"old": old}, clock=lambda: 101)
    assert rotated.decode(token) == {"id": "7"}
    for codec in (
        CursorCodec(new, context="p", clock=lambda: 101),
        CursorCodec(old, key_id="old", context="p", clock=lambda: 1000),
        CursorCodec(old, key_id="old", context="p", clock=lambda: 0),
    ):
        with pytest.raises(ValidationFailedError):
            codec.decode(token)


def test_context_binds_scope_query_and_current_authority() -> None:
    tenant, company, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def context(**changes: object) -> str:
        return cursor_context(
            resource="items",
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            authority_version=str(changes.get("authority", "1")),
            query={"sort": "sku", "status": changes.get("status", "active")},
        )

    codec = CursorCodec(secrets.token_bytes(32), context=context())
    assert context() != context(authority="2")
    assert context() != context(status="draft")
    assert codec.decode(codec.encode({"id": "7"})) == {"id": "7"}
    with pytest.raises(ValueError):
        cursor_context(
            resource="items",
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            authority_version="",
            query={},
        )


@pytest.mark.parametrize("token", ["", "!", "a" * 4097, "YQ", "YQ=="])
def test_malformed_and_oversized_tokens(token: str) -> None:
    with pytest.raises(ValidationFailedError):
        CursorCodec(secrets.token_bytes(32), context="p").decode(token)


@pytest.mark.parametrize(
    "body",
    [
        b'{"v":2,"v":2}',
        b'{"values":NaN}',
        b"{}",
        b'{"v":2,"kid":"current","ctx":"p","iat":100,"exp":1000,"values":[]}',
        b'{"v":2,"kid":"current","ctx":"p","iat":true,"exp":1000,"values":{}}',
        b'{"v":2,"kid":"current","ctx":"p","iat":100,"exp":10000,"values":{}}',
        b'{"v":2,"kid":"wrong","ctx":"p","iat":100,"exp":1000,"values":{}}',
        b'{"v":1,"ctx":"p","values":{}}',
    ],
)
def test_authenticated_invalid_payloads(body: bytes) -> None:
    key = secrets.token_bytes(32)
    token = (
        base64.urlsafe_b64encode(body + hmac.digest(key, body, hashlib.sha256))
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(ValidationFailedError):
        CursorCodec(key, context="p", clock=lambda: 100).decode(token)


def test_configuration_and_output_bounds() -> None:
    key = secrets.token_bytes(32)
    for arguments in (
        {"ttl_seconds": 0},
        {"ttl_seconds": True},
        {"key_id": "bad.key"},
        {"verification_keys": {"current": secrets.token_bytes(32)}},
        {"verification_keys": {str(n): key for n in range(5)}},
    ):
        with pytest.raises(ValueError):
            CursorCodec(key, context="p", **arguments)
    with pytest.raises(ValueError):
        CursorCodec(key, context="p").encode({"id": "x" * 4096})
