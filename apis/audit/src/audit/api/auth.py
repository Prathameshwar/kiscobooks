"""Audit adapter for the shared verifier of the existing signed gateway context."""

from collections.abc import AsyncIterator

from billing_platform.audit_context import audit_actor, audit_request
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor as Actor
from billing_platform.gateway import decode_actor_context as _decode_actor
from fastapi import Header, Request


async def actor(
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
) -> AsyncIterator[Actor]:
    if x_actor_context is None or x_actor_signature is None:
        raise AuthenticationRequiredError("actor context is required")
    secret: bytes = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    current = _decode_actor(x_actor_context, x_actor_signature, secret)
    if current.impersonation_id and request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions allow read requests only")
    with (
        audit_actor(current.real_user_id, current.user_id),
        audit_request(request.headers.get("x-trace-id"), request.headers.get("x-request-id")),
    ):
        yield current
