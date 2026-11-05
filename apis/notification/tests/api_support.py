"""Helpers for driving the notification FastAPI app in tests.

The gateway signs the actor context in production; here a test mints one the same way so
a route's authorization is exercised end to end. Throwaway constants for an in-process
app — no live server, no real key (CLAUDE.md §5.9). The signed body uses the shared
scoped-grant contract; management requires tenant scope.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

ACTOR_SECRET = "test-actor-signing-secret-not-a-real-secret"
CURSOR_SECRET = "test-cursor-signing-secret-not-a-real-secret-000"
#: 32 bytes so the app uses it directly as the AES-GCM data key.
DATA_KEY = "test-data-encryption-key-32bytes!"


def actor_headers(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: list[str] | None = None,
    secret: str = ACTOR_SECRET,
    issued_at: int | None = None,
    company_id: uuid.UUID | None = None,
) -> dict[str, str]:
    body = json.dumps(
        {
            "issued_at": int(issued_at if issued_at is not None else time.time()),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "grants": [
                {
                    "permissions": permissions or [],
                    "scope_type": "company" if company_id is not None else "tenant",
                    "scope_id": str(company_id) if company_id is not None else None,
                    "valid_from": "2000-01-01",
                }
            ],
        }
    ).encode()
    token = base64.urlsafe_b64encode(body).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Actor-Context": token, "X-Actor-Signature": signature}
