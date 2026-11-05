"""Authentication: the gateway-signed actor context, verified and never minted here.

**Why actor context only.** Identity signs a *company* context for the accounting,
vouchers and reports gateway routes, because those requests need resolved financial facts
and field policies (``identity/api/login.py``). A design request needs neither: it needs
the caller's resolved grants, which the actor context carries, and the company in the
path, which every route checks those grants against (``api/authorization.py``). Requiring
a company context this gateway does not issue would 401 every request; accepting one
*optionally* would be worse, because the scope check could then be skipped by omitting the
header — which is the hole this file was rewritten to close.

There is no test-header fallback. A header that authenticates without a signature is an
authentication bypass wherever the setting meant to gate it is missing; tests sign their
contexts through the same code path production verifies (``tests/conftest.py``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from billing_platform.audit_context import audit_actor, audit_request
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor, decode_actor_context
from fastapi import Header, Request


@dataclass(frozen=True, slots=True)
class Access:
    """The verified caller. Authorization is a separate, per-route step."""

    actor: Actor


async def access(
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
) -> AsyncIterator[Access]:
    """Verify the signed actor context and bind this request's audit correlation."""
    if x_actor_context is None or x_actor_signature is None:
        raise AuthenticationRequiredError("actor context is required")
    settings = request.app.state.settings
    secret = settings.actor_signing_secret.get_secret_value().encode()
    actor = decode_actor_context(x_actor_context, x_actor_signature, secret)

    # Support sessions read; they never change a tenant's designs (docs/org-model.md §7).
    if actor.impersonation_id and request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions are read only")

    if request.method not in {"GET", "HEAD"}:
        limiter = getattr(request.app.state, "write_limiter", None)
        if limiter is not None and not limiter.allow(
            f"{actor.tenant_id}:{actor.user_id}", limit=settings.write_rate_limit
        ):
            raise PermissionDeniedError("write rate limit exceeded")

    with (
        audit_actor(actor.real_user_id, actor.user_id),
        audit_request(request.headers.get("x-trace-id"), request.headers.get("x-request-id")),
    ):
        yield Access(actor=actor)
