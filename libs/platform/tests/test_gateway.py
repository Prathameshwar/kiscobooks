import base64
import datetime as dt
import hashlib
import hmac
import json
import time
from typing import Any

import pytest

from billing_platform.authz import ScopePath
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7

SECRET = b"ephemeral-gateway-test-key-not-a-live-secret"


def decode(value: Any) -> Any:
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    return decode_actor_context(
        base64.urlsafe_b64encode(body).rstrip(b"=").decode(),
        hmac.new(SECRET, body, hashlib.sha256).hexdigest(),
        SECRET,
    )


def context() -> dict[str, Any]:
    return {"issued_at": int(time.time()), "tenant_id": str(uuid7()), "user_id": str(uuid7())}


def grant(**values: Any) -> dict[str, Any]:
    return {
        "permissions": ["item.read"],
        "scope_type": "tenant",
        "scope_id": None,
        "valid_from": "2000-01-01",
        **values,
    }


def test_verified_actor_requires_both_permission_and_reachable_scope() -> None:
    company = uuid7()
    current = decode({**context(), "grants": [grant(scope_type="company", scope_id=str(company))]})
    current.require("item.read")
    current.require_scope("item.read", target=ScopePath(company_id=company))
    assert current.allows_scope("item.read", target=ScopePath(company_id=company))
    assert not current.allows_scope("item.read", target=ScopePath(company_id=uuid7()))
    with pytest.raises(PermissionDeniedError):
        current.require("item.create")


def test_expired_revoked_and_future_grants_do_not_grant_permission() -> None:
    current = decode(
        {
            **context(),
            "grants": [
                grant(valid_to="2001-01-01"),
                grant(is_active=False),
                grant(valid_from="9999-01-01"),
            ],
        }
    )
    assert current.permissions == frozenset()
    with pytest.raises(PermissionDeniedError):
        current.require_scope("item.read", target=ScopePath(), on_date=dt.date.today())


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"issued_at": "1"},
        {"issued_at": True},
        {"issued_at": 0},
        {"issued_at": 999999999999},
        {"tenant_id": "invalid"},
        {"tenant_id": "00000000-0000-0000-0000-000000000000"},
        {"grants": [grant(is_active="false")]},
        {"grants": [grant(permissions="item.read")]},
        {"grants": [grant(scope_type="platform")]},
        {"grants": [grant(scope_type="company")]},
        {"grants": [grant(valid_to="1999-01-01")]},
        {"grants": [grant(extra="ignored?")]},
        {"permissions": ["item.read"]},
        {"group_ids": ["bad"]},
    ],
)
def test_malformed_signed_context_always_becomes_401(bad: Any) -> None:
    value = {**context(), **bad} if isinstance(bad, dict) and bad else bad
    with pytest.raises(AuthenticationRequiredError, match="invalid or expired"):
        decode(value)


def test_tampering_duplicate_keys_and_encoding_errors() -> None:
    for token, signature in [
        ("!", "0" * 64),
        ("x" * 32769, "0" * 64),
        ("e30", "0" * 64),
        ("e30", "bad"),
        ("e30", "é" * 64),
    ]:
        with pytest.raises(AuthenticationRequiredError):
            decode_actor_context(token, signature, SECRET)
    with pytest.raises(AuthenticationRequiredError):
        decode(b'{"tenant_id":"first","tenant_id":"second"}')
    with pytest.raises(AuthenticationRequiredError):
        decode(b"[" * 2000 + b"]" * 2000)


def test_retained_actor_subject_has_no_permission_authority_and_live_context_stays_expired():
    from billing_platform.gateway import verify_retained_actor_subject

    value = {**context(), "issued_at": int(time.time()) - 86400, "grants": [grant()]}
    raw = json.dumps(value).encode()
    token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    signature = hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
    with pytest.raises(AuthenticationRequiredError):
        decode_actor_context(token, signature, SECRET)
    retained = verify_retained_actor_subject(token, signature, SECRET)
    assert (
        str(retained.tenant_id) == value["tenant_id"] and str(retained.user_id) == value["user_id"]
    )
    assert not hasattr(retained, "require_scope") and not hasattr(retained, "grants")
    with pytest.raises(AuthenticationRequiredError):
        verify_retained_actor_subject(token, "0" * 64, SECRET)
