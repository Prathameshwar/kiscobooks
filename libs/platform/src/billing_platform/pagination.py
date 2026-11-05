"""Safe, opaque keyset pagination shared by list APIs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from billing_platform.errors import ValidationFailedError

DEFAULT_PAGE_SIZE: Final[int] = 50
MAX_PAGE_SIZE: Final[int] = 200


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValidationFailedError(
                "invalid page size", fields={"limit": f"must be between 1 and {MAX_PAGE_SIZE}"}
            )


class CursorCodec:
    """Bounded, expiring HMAC cursors with a small verification key ring.

    Context must include current query, scope and authority (see cursor_context).
    A cursor never grants authority; authenticate and resolve policies each page.
    Version 1 cursors had no expiry and are intentionally rejected; restart paging.
    """

    def __init__(
        self,
        secret: bytes,
        *,
        context: str,
        key_id: str = "current",
        verification_keys: Mapping[str, bytes] | None = None,
        ttl_seconds: int = 900,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("cursor secret must contain at least 32 bytes")
        if not context:
            raise ValueError("cursor context is required")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise ValueError("cursor lifetime must be between 1 and 86400 seconds")
        keys = dict(verification_keys or {})
        if key_id in keys and keys[key_id] != secret:
            raise ValueError("active cursor key conflicts with verification key")
        keys[key_id] = secret
        if len(keys) > 4 or any(
            not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", kid) or len(key) < 32
            for kid, key in keys.items()
        ):
            raise ValueError("invalid cursor verification key ring")
        self._secret = secret
        self._context = context
        self._key_id = key_id
        self._keys = keys
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def encode(self, values: dict[str, Any]) -> str:
        now = int(self._clock())
        body = json.dumps(
            {
                "v": 2,
                "kid": self._key_id,
                "ctx": self._context,
                "iat": now,
                "exp": now + self._ttl_seconds,
                "values": values,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        signature = hmac.digest(self._secret, body, hashlib.sha256)
        token = base64.urlsafe_b64encode(body + signature).rstrip(b"=").decode("ascii")
        if len(token) > 4096:
            raise ValueError("cursor exceeds maximum size")
        return token

    def decode(self, token: str) -> dict[str, Any]:
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 4096:
                raise ValueError
            if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
                raise ValueError
            raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != token:
                raise ValueError
            body, signature = raw[:-32], raw[-32:]
            # Verify bounded bytes before parsing attacker-controlled JSON. Four
            # keys at most; key identity is verified again after authentication.
            matched = {
                kid
                for kid, key in self._keys.items()
                if hmac.compare_digest(signature, hmac.digest(key, body, hashlib.sha256))
            }
            if not body or not matched:
                raise ValueError
            payload = json.loads(
                body, object_pairs_hook=_unique_object, parse_constant=_no_constant
            )
            if not isinstance(payload, dict) or set(payload) != {
                "v",
                "kid",
                "ctx",
                "iat",
                "exp",
                "values",
            }:
                raise ValueError
            if (
                payload["v"] != 2
                or payload["ctx"] != self._context
                or payload["kid"] not in matched
            ):
                raise ValueError
            issued, expires, now = payload["iat"], payload["exp"], int(self._clock())
            if type(issued) is not int or type(expires) is not int:
                raise ValueError
            if issued > now + 30 or expires <= now or not 0 < expires - issued <= self._ttl_seconds:
                raise ValueError
            values = payload["values"]
            if not isinstance(values, dict):
                raise ValueError
            return values
        except (ValueError, KeyError, TypeError, RecursionError) as exc:
            raise ValidationFailedError(
                "invalid cursor", fields={"cursor": "malformed, expired, or for another list"}
            ) from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _no_constant(value: str) -> None:
    raise ValueError("nonfinite JSON number")


def cursor_context(
    *,
    resource: str,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
    authority_version: str,
    query: Mapping[str, Any],
) -> str:
    """Hash normalized, service-validated query and *current* policy identity.

    Include resolved filters/search/sort/projection/schema versions in query;
    exclude the cursor itself. Authority version must change on a relevant revoke.
    """
    if (
        not resource
        or not authority_version
        or any(value.int == 0 for value in (tenant_id, company_id, actor_id))
    ):
        raise ValueError("cursor requires resource, scoped subject and current authority")
    body = json.dumps(
        [resource, str(tenant_id), str(company_id), str(actor_id), authority_version, dict(query)],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(body).hexdigest()


def validate_sort(sort: str, *, allowed: frozenset[str], default: str) -> tuple[str, bool]:
    """Return ``(field, descending)`` after enforcing a service-owned allowlist."""
    value = sort or default
    descending = value.startswith("-")
    field = value[1:] if descending else value
    if field not in allowed:
        raise ValidationFailedError(
            "unsupported sort field", fields={"sort": f"allowed: {', '.join(sorted(allowed))}"}
        )
    return field, descending
