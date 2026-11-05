"""Shared Redis mechanism (CLAUDE.md §3: the library holds mechanism, services hold policy).

Redis is **cache-only** on this platform (docs/tech-stack.md) — the broker is RabbitMQ.
Every service that needs a short-lived key/value store builds its client through
:func:`create_redis_client` and wraps it in :class:`RedisCache`. Two current consumers
build on this: the permission-resolution cache (org-model §5.2, the union of a user's
grants, invalidated on ``role_assignment.changed``) and identity's step-up proof store.

**One primitive, two failure policies — the caller chooses, because the safe direction
differs:**

* **Fail-open** (a cache): a Redis outage must degrade to the source of truth. It may
  never block a request and never widen access. The read-through pattern catches
  :class:`CacheUnavailableError` and falls back to the loader.
* **Fail-closed** (a security proof, e.g. step-up): the caller lets the error surface
  as a 503, because proceeding *without* the proof would be unsafe.

``RedisCache`` maps ``redis.exceptions.RedisError`` to :class:`CacheUnavailableError`
so neither policy has to know the driver's exception type. It stores strings only —
callers serialize their own values (identity uses ``authz.encode_grants``). Redis holds
no source of truth here, so nothing in it is authoritative and, per CLAUDE.md §5.11,
no PII belongs in a cache value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from billing_platform.errors import PlatformError

if TYPE_CHECKING:
    from redis.asyncio import Redis

try:  # redis is the optional `cache` extra; importing platform must not require it.
    from redis.exceptions import RedisError
except ModuleNotFoundError:  # pragma: no cover - exercised only without the extra
    class RedisError(Exception):  # type: ignore[no-redef]
        """Placeholder so ``except RedisError`` is valid when redis is not installed."""


#: Bounded so a slow or unreachable Redis fails fast into the caller's fallback rather
#: than holding a request open. Two seconds is generous on a loopback cache.
DEFAULT_CONNECT_TIMEOUT: float = 2.0
DEFAULT_SOCKET_TIMEOUT: float = 2.0


class CacheUnavailableError(PlatformError):
    """The cache backend could not be reached.

    A fail-open caller catches this and falls back to the source of truth; a
    fail-closed caller lets it surface as the 503 it is.
    """

    status_code = 503
    code = "cache_unavailable"


def create_redis_client(
    url: str,
    *,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    socket_timeout: float = DEFAULT_SOCKET_TIMEOUT,
    decode_responses: bool = True,
) -> Redis:
    """The one place a service constructs its Redis client.

    ``decode_responses=True`` because every value on this platform is text (JSON or a
    token); a caller that needs bytes passes ``decode_responses=False``. Timeouts are
    bounded (see the module constants) so a cache outage degrades quickly.
    """
    from redis.asyncio import Redis

    client: Redis = Redis.from_url(
        url,
        decode_responses=decode_responses,
        socket_connect_timeout=connect_timeout,
        socket_timeout=socket_timeout,
    )
    return client


class RedisCache:
    """A namespaced string cache over a Redis client.

    ``namespace`` prefixes every key (``"identity:authz"`` → ``identity:authz:<key>``)
    so unrelated caches sharing one Redis instance cannot collide, and a flush of one
    concern never touches another. All operations raise :class:`CacheUnavailableError`
    on a backend failure; the caller decides fail-open vs fail-closed.
    """

    def __init__(self, client: Redis, *, namespace: str) -> None:
        self.client = client
        self._namespace = namespace.rstrip(":")

    def _scoped(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def get(self, key: str) -> str | None:
        try:
            value = await self.client.get(self._scoped(key))
        except RedisError as exc:
            raise CacheUnavailableError("cache backend is unavailable") from exc
        return value if isinstance(value, str) else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self.client.set(self._scoped(key), value, ex=ttl_seconds)
        except RedisError as exc:
            raise CacheUnavailableError("cache backend is unavailable") from exc

    async def take(self, key: str) -> str | None:
        """Atomically read and delete — a single-use value (a one-shot proof)."""
        try:
            value = await self.client.getdel(self._scoped(key))
        except RedisError as exc:
            raise CacheUnavailableError("cache backend is unavailable") from exc
        return value if isinstance(value, str) else None

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self.client.delete(*(self._scoped(k) for k in keys))
        except RedisError as exc:
            raise CacheUnavailableError("cache backend is unavailable") from exc

    async def close(self) -> None:
        await self.client.aclose()


__all__ = [
    "DEFAULT_CONNECT_TIMEOUT",
    "DEFAULT_SOCKET_TIMEOUT",
    "CacheUnavailableError",
    "RedisCache",
    "RedisError",
    "create_redis_client",
]
