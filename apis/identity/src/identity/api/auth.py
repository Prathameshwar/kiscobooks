"""Authentication boundary: the gateway-resolved, signed actor context.

CLAUDE.md §5.4 — the JWT carries only ``tenant_id`` / ``user_id`` / ``user_type``,
never the permission set. The scope-aware *grants* are resolved server-side from the
permission cache at the gateway and handed to the service as a short-lived,
HMAC-signed context header, so revocation takes effect on the cache TTL rather than
the token TTL. This module verifies that signature (over the raw body, with a
timestamp window against replay) and rebuilds the grants the authorization layer
reasons about.

Two checks hang off the ``Actor``, and both are mandatory (CLAUDE.md §5.2):

* :meth:`Actor.require` — the **endpoint gate**: does the actor hold this permission
  at *any* scope. Necessary, never sufficient.
* :meth:`Actor.require_scope` — the **object-level** check: is the permission held at
  a scope that reaches the object being touched. §5.2 names this the most likely real
  vulnerability, so it is a distinct call a route cannot satisfy by holding the
  endpoint key alone.

A route that mutates or reads one company's data calls both. Cross-*tenant* access is
already impossible — the session filter hides other tenants' rows entirely — so the
object-level check is about the wrong *company or department within the same tenant*.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from billing_platform.authz import Grant, Scope, ScopePath, assert_permitted
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.oidc import AccessTokenVerifier, VerifiedClaims
from fastapi import Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain import authorization

#: The signed context is rejected if its ``issued_at`` is more than this many seconds
#: from now, in either direction — a stolen header is useless once it is stale, and a
#: clock far in the future is as suspect as one far in the past.
_MAX_CONTEXT_AGE_SECONDS = 60


@dataclass(slots=True)
class Actor:
    """Who is acting, and the scope-aware permissions they hold right now."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    #: Resolved server-side and passed in — never read from the request body, which
    #: would let a caller certify their own authority (see ``domain/authorization``).
    grants: tuple[Grant, ...] = ()
    #: Every group the actor belongs to. Feeds the self-modification guard on role
    #: assignment; empty is the safe-in-one-direction default the gateway must fill.
    group_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    real_user_id: uuid.UUID | None = None
    real_tenant_id: uuid.UUID | None = None
    impersonation_id: uuid.UUID | None = None
    impersonation_expires_at: int | None = None

    @property
    def permissions(self) -> frozenset[str]:
        """The union of everything held at any scope — the endpoint-gate set.

        Deliberately scope-blind: this answers "could this actor ever do X", which is
        the coarse gate. Whether they may do it *to this object* is
        :meth:`require_scope`, which reasons about scope and validity.
        """
        held: set[str] = set()
        today = utcnow().date()
        for grant in self.grants:
            if (
                grant.is_active
                and grant.valid_from <= today
                and (grant.valid_to is None or today <= grant.valid_to)
            ):
                held |= grant.permissions
        return frozenset(held)

    def require(self, permission: str) -> None:
        """Endpoint gate. Raises 403 if the actor holds ``permission`` at no scope."""
        if permission not in self.permissions:
            raise PermissionDeniedError(f"this action requires {permission}")

    def require_scope(
        self, permission: str, *, target: ScopePath, on_date: dt.date | None = None
    ) -> None:
        """Object-level check. Raises 403 unless ``permission`` is held at a scope
        that is an ancestor-or-self of ``target`` and in force on ``on_date``."""
        assert_permitted(
            self.grants,
            permission,
            target=target,
            on_date=on_date or utcnow().date(),
        )

    def as_domain_actor(self) -> authorization.Actor:
        """The value the escalation guards in ``domain/authorization`` operate on."""
        return authorization.Actor(
            user_id=self.user_id, grants=self.grants, group_ids=self.group_ids
        )


def _grant_from(raw: dict[str, Any]) -> Grant:
    """One signed grant entry into an :class:`authz.Grant`.

    ``scope_id`` is ``null`` on the wire for a tenant-wide grant and becomes the
    ``SCOPE_ALL`` sentinel here — the API boundary speaks ``null``, the resolver speaks
    the sentinel (plan §2).
    """
    scope_id_raw = raw.get("scope_id")
    scope = Scope(
        scope_type=str(raw["scope_type"]),
        scope_id=SCOPE_ALL if scope_id_raw is None else uuid.UUID(str(scope_id_raw)),
    )
    valid_to_raw = raw.get("valid_to")
    return Grant(
        permissions=frozenset(str(p) for p in raw["permissions"]),
        scope=scope,
        valid_from=dt.date.fromisoformat(str(raw["valid_from"])),
        valid_to=None if valid_to_raw is None else dt.date.fromisoformat(str(valid_to_raw)),
        is_active=bool(raw.get("is_active", True)),
    )


def _decode_actor(token: str, signature: str, secret: bytes) -> Actor:
    from billing_platform.gateway import decode_actor_context

    decoded = decode_actor_context(token, signature, secret)
    if decoded.impersonation_id is not None:
        raise AuthenticationRequiredError(
            "Identity support access requires verified OIDC authentication"
        )
    return Actor(decoded.tenant_id, decoded.user_id, decoded.grants, group_ids=decoded.group_ids)


async def actor(
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Actor:
    if authorization is not None and authorization.startswith("Bearer jpat_"):
        from identity.services.tokens import authenticate_token

        current = await authenticate_token(request, authorization[7:])
        request.state.actor = current
        return current
    verifier: AccessTokenVerifier | None = request.app.state.token_verifier
    if verifier is not None:
        # In OIDC mode, externally supplied actor headers never authenticate a request.
        claims = await verified_claims(request, authorization)
        from identity.models import User
        from identity.services.login import locate_subject

        async with request.app.state.session_factory() as lookup:
            tenant_id = await locate_subject(lookup, claims)
        with tenant_scope(tenant_id):
            async with request.app.state.session_factory() as db:
                user_id = await db.scalar(select(User.id).where(User.authentik_sub == claims.sub))
                if user_id is None:
                    raise AuthenticationRequiredError("identity is unavailable")
                current = Actor(tenant_id, user_id)
                request.state.verified_claims = claims
                await refresh_current(db, request, current)
        # Close the authentication read transaction before an endpoint opens its own.
        if request.headers.get("x-impersonation-session"):
            from identity.services.impersonation import apply_impersonation

            current = await apply_impersonation(request, current)
        request.state.actor = current
        return current
    # Optional at the framework layer so a missing header is our 401, not FastAPI's
    # 422 for a missing required field — the difference the test matrix (§7) asserts.
    if x_actor_context is None or x_actor_signature is None:
        raise AuthenticationRequiredError("actor context is required")
    secret: bytes = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    current = _decode_actor(x_actor_context, x_actor_signature, secret)
    request.state.actor = current
    return current


async def refresh_current(db: AsyncSession, request: Request, current: Actor) -> None:
    """Refresh the request-local grant holder inside the caller's locked transaction."""
    if current.impersonation_id is not None:
        from identity.services.impersonation import refresh_impersonation

        await refresh_impersonation(db, request, current)
        return
    if getattr(request.state, "api_token_id", None) is not None:
        from identity.services.tokens import refresh_token

        await refresh_token(db, request, current)
        return
    claims: VerifiedClaims | None = getattr(request.state, "verified_claims", None)
    if claims is None:
        return  # Existing trusted-gateway deployments use the signed 60-second context.
    from identity.models import Tenant, User
    from identity.services.login import live_grants

    user = await db.get(User, current.user_id)
    tenant = await db.get(Tenant, current.tenant_id)
    if (
        user is None
        or user.authentik_sub != claims.sub
        or user.status != "active"
        or tenant is None
        or tenant.status == "closed"
        or claims.exp <= int(time.time())
        or (
            user.tokens_valid_after_at is not None
            and (
                claims.auth_time is None
                or claims.auth_time <= user.tokens_valid_after_at.timestamp()
                or claims.iat <= user.tokens_valid_after_at.timestamp()
            )
        )
    ):
        raise AuthenticationRequiredError("identity is inactive or access was revoked")
    if tenant.status != "active" and request.url.path != "/v1/session":
        raise PermissionDeniedError("tenant is suspended")
    # Grants come from the Redis permission cache when it is configured, falling back to
    # a live resolution otherwise (org-model §5.2, CLAUDE.md §5.4). The user/tenant rows
    # above are always read live, so activation and token revocation are never cached —
    # only the resolved grant set is.
    grant_cache = getattr(request.app.state, "grant_cache", None)
    if grant_cache is not None:
        grants, groups = await grant_cache.resolve(db, current.tenant_id, user.id)
    else:
        grants, groups = await live_grants(db, user.id)
    # A new holder is created for every request. Only authority is refreshed; the
    # verified tenant/user identity stays fixed across dependencies and command callbacks.
    current.grants = grants if tenant.status == "active" else ()
    current.group_ids = groups


async def verified_claims(request: Request, authorization: str | None) -> VerifiedClaims:
    verifier: AccessTokenVerifier | None = request.app.state.token_verifier
    if verifier is None or authorization is None or not authorization.startswith("Bearer "):
        raise AuthenticationRequiredError("a provider access token is required")
    return await verifier.verify(authorization[7:])
