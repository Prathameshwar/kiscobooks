"""Helpers for driving the FastAPI app in tests.

The gateway is what signs the actor context in production; here the test mints one the
same way, so a route's authorization is exercised end to end rather than mocked. The
secrets are throwaway constants for an in-process app — no live server, no network, no
real key (CLAUDE.md §5.9).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

#: HMAC key the app is configured with and the signer signs with. Any length is fine
#: for HMAC; the cursor secret must be >=32 bytes (``CursorCodec``).
ACTOR_SECRET = "test-actor-signing-secret-not-a-real-secret"
CURSOR_SECRET = "test-cursor-signing-secret-not-a-real-secret-000"


def grant(
    permissions: list[str],
    *,
    scope_type: str = "tenant",
    scope_id: uuid.UUID | None = None,
    valid_from: str = "2000-01-01",
    valid_to: str | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    """One grant as the signed context encodes it. ``scope_id`` is ``None`` (→ tenant
    scope) or a real id at company/department scope."""
    return {
        "permissions": permissions,
        "scope_type": scope_type,
        "scope_id": None if scope_id is None else str(scope_id),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "is_active": is_active,
    }


def actor_headers(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    grants: list[dict[str, Any]] | None = None,
    group_ids: list[uuid.UUID] | None = None,
    secret: str = ACTOR_SECRET,
    issued_at: int | None = None,
) -> dict[str, str]:
    """The ``X-Actor-Context`` / ``X-Actor-Signature`` pair for a request."""
    body = json.dumps(
        {
            "issued_at": int(issued_at if issued_at is not None else time.time()),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "grants": grants or [],
            "group_ids": [str(g) for g in (group_ids or [])],
        }
    ).encode()
    token = base64.urlsafe_b64encode(body).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Actor-Context": token, "X-Actor-Signature": signature}
