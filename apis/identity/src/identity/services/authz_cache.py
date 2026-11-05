"""The permission-resolution cache (org-model §5.2, CLAUDE.md §5.4).

The JWT never carries the permission set. A user's effective grants resolve
server-side, per request, from this cache — so revocation takes effect on the cache
TTL rather than the token TTL. The cache fronts :func:`identity.services.login.live_grants`,
the ~3-query database resolution that nginx would otherwise trigger on every
``gateway_authorize`` subrequest.

**This is a cache, not a source of truth**, and it fails *open*: a Redis outage (or a
poisoned entry) falls back to a live database resolution. It never blocks a request and
never widens access — the loader is the authority, the cache only saves it work. That
is the opposite of the step-up proof store, which fails *closed* because proceeding
without the proof would be unsafe.

**Invalidation is TTL + user-targeted** (the agreed v1). A grant change to a specific
user (a role assignment granted/revoked/regranted against that user, or a group
membership change) eagerly deletes that user's entry so the change is immediate.
Broader changes — a group-subject assignment, or an edit to a role's permission set —
are bounded by the TTL, the documented staleness window. Note that *user* activation
and token revocation are not cached at all: ``api/auth.refresh_current`` re-reads the
live ``user``/``tenant`` rows every request and only the resolved grants come from here.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from billing_platform.authz import Grant, decode_grants, encode_grants
from billing_platform.cache import CacheUnavailableError, RedisCache

from identity.services.login import live_grants

_LOG = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

#: Keyspace for this cache; ``RedisCache`` prefixes every key with it.
NAMESPACE = "identity:authz"


class GrantCache:
    """Read-through cache of ``(grants, groups)`` keyed by ``tenant:user``."""

    def __init__(self, cache: RedisCache, *, ttl_seconds: int) -> None:
        self._cache = cache
        self._ttl = ttl_seconds

    @staticmethod
    def _key(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
        # Tenant-namespaced even though user ids are globally unique: it keeps a
        # tenant's authority data grouped and unambiguous under one keyspace.
        return f"{tenant_id}:{user_id}"

    async def resolve(
        self, db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[tuple[Grant, ...], frozenset[uuid.UUID]]:
        """Cached grants for the user, or a live resolution on miss/outage.

        Fail-open at every step: a cache read error, a poisoned entry, or a populate
        error all degrade to the database — never a 5xx and never a widened grant set.
        """
        key = self._key(tenant_id, user_id)
        try:
            cached = await self._cache.get(key)
        except CacheUnavailableError:
            cached = None
        if cached is not None:
            try:
                return decode_grants(cached)
            except ValueError:
                pass  # poisoned / version-skewed entry: fall through and re-resolve
        grants, groups = await live_grants(db, user_id)
        try:
            await self._cache.set(key, encode_grants(grants, groups), self._ttl)
        except CacheUnavailableError:
            pass  # populating the cache is best-effort; the request already has its answer
        return grants, groups

    async def invalidate(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Drop a user's entry so the next request re-resolves. On outage the TTL
        is the backstop; log the failure without failing a committed write."""
        try:
            await self._cache.delete(self._key(tenant_id, user_id))
        except CacheUnavailableError:
            _LOG.warning("permission cache invalidation failed; TTL is the backstop")


def schedule_invalidation(request: Request, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Register a *post-commit* invalidation of one user's cached grants.

    Deferred to after commit (via ``request.state.after_commit``, run by the session
    dependency) rather than done inline: invalidating before commit would let a
    concurrent request repopulate the entry from the not-yet-committed old state. A
    no-op when the cache is not configured.
    """
    cache: GrantCache | None = getattr(request.app.state, "grant_cache", None)
    if cache is None:
        return
    hooks = getattr(request.state, "after_commit", None)
    if hooks is None:
        hooks = []
        request.state.after_commit = hooks

    async def _invalidate() -> None:
        await cache.invalidate(tenant_id, user_id)

    hooks.append(_invalidate)
