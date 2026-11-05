"""Shared signed gateway context. Notification management requires tenant scope."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from billing_platform.audit_context import audit_actor
from billing_platform.authz import ScopePath
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor as GatewayActor
from billing_platform.gateway import decode_actor_context
from fastapi import Header, Request


@dataclass(frozen=True, slots=True)
class Actor:
    context: GatewayActor
    platform: bool = False

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.context.tenant_id

    @property
    def user_id(self) -> uuid.UUID:
        return self.context.user_id

    def require(self, permission: str) -> None:
        self.context.require_scope(
            "platform." + permission.replace("notification.", "notification_", 1)
            if self.platform
            else permission,
            target=ScopePath(),
        )

    def require_endpoint(self, permission: str) -> None:
        key = (
            "platform." + permission.replace("notification.", "notification_", 1)
            if self.platform
            else permission
        )
        self.context.require(key)

    def require_company(self, permission: str, company_id: uuid.UUID) -> None:
        self.context.require_scope(
            "platform." + permission.replace("notification.", "notification_", 1)
            if self.platform
            else permission,
            target=ScopePath(company_id=company_id),
        )


def _decode_actor(token: str, signature: str, secret: bytes) -> Actor:
    return Actor(decode_actor_context(token, signature, secret))


async def actor(
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
) -> AsyncIterator[Actor]:
    if x_actor_context is None or x_actor_signature is None:
        raise AuthenticationRequiredError("actor context is required")
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    current = _decode_actor(x_actor_context, x_actor_signature, secret)
    is_platform = request.url.path.startswith("/v1/platform/")
    marker = current.context.user_type == "platform_notification_operator"
    settings = request.app.state.settings
    authority = current.context.notification_authority
    if is_platform:
        if (
            not marker
            or authority is None
            or authority.path != request.url.path
            or authority.method != request.method
            or current.context.impersonation_id
            or settings.platform_owner_tenant_id != current.tenant_id
            or not settings.platform_space_id
            or settings.platform_space_id == current.tenant_id
        ):
            raise PermissionDeniedError("verified platform notification authority is required")
        current = Actor(current.context, platform=True)
    elif marker:
        raise PermissionDeniedError("platform authority is bound to the platform surface")
    if current.context.impersonation_id and request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions permit reads only")
    request.state.notification_actor = current
    with audit_actor(current.context.real_user_id, current.user_id):
        yield current
