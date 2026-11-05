"""The shared Redis cache mechanism.

No live Redis: the client is a mock with ``AsyncMock`` methods, the same pattern the
identity step-up adapter test uses. What matters here is the *contract* every consumer
relies on — namespacing, and the mapping of a driver ``RedisError`` to the platform's
:class:`CacheUnavailableError` so a fail-open caller can catch one type and a
fail-closed caller can let the 503 surface.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from billing_platform.cache import CacheUnavailableError, RedisCache, create_redis_client


def _mock_client(**overrides: object) -> SimpleNamespace:
    base = {
        "get": AsyncMock(return_value=None),
        "set": AsyncMock(),
        "getdel": AsyncMock(return_value=None),
        "delete": AsyncMock(),
        "aclose": AsyncMock(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_create_redis_client_uses_bounded_timeouts_and_text_mode():
    client = create_redis_client("redis://127.0.0.1:6379/0")
    try:
        kwargs = client.connection_pool.connection_kwargs
        # decode_responses=True keeps values as str across the platform.
        assert kwargs["decode_responses"] is True
        # Bounded so a cache outage fails fast into the caller's fallback.
        assert kwargs["socket_connect_timeout"] == 2.0
        assert kwargs["socket_timeout"] == 2.0
    finally:
        await client.aclose()


async def test_namespacing_prefixes_every_key():
    client = _mock_client(get=AsyncMock(return_value="v"))
    cache = RedisCache(client, namespace="identity:authz")

    await cache.get("tenant:user")
    client.get.assert_awaited_once_with("identity:authz:tenant:user")

    await cache.set("tenant:user", "payload", 30)
    client.set.assert_awaited_once_with("identity:authz:tenant:user", "payload", ex=30)

    await cache.delete("a", "b")
    client.delete.assert_awaited_once_with("identity:authz:a", "identity:authz:b")


async def test_trailing_colon_in_namespace_is_normalized():
    client = _mock_client(get=AsyncMock(return_value=None))
    cache = RedisCache(client, namespace="ns:")
    await cache.get("k")
    client.get.assert_awaited_once_with("ns:k")


async def test_get_returns_none_for_missing_or_non_string():
    cache = RedisCache(_mock_client(get=AsyncMock(return_value=None)), namespace="ns")
    assert await cache.get("missing") is None
    # A stray non-string value is treated as absent rather than surfaced.
    cache = RedisCache(_mock_client(get=AsyncMock(return_value=42)), namespace="ns")
    assert await cache.get("odd") is None


async def test_take_is_atomic_read_and_delete():
    client = _mock_client(getdel=AsyncMock(return_value="once"))
    cache = RedisCache(client, namespace="ns")
    assert await cache.take("k") == "once"
    client.getdel.assert_awaited_once_with("ns:k")


async def test_delete_with_no_keys_is_a_noop():
    client = _mock_client()
    cache = RedisCache(client, namespace="ns")
    await cache.delete()
    client.delete.assert_not_awaited()


@pytest.mark.parametrize("op", ["get", "set", "take", "delete"])
async def test_backend_error_maps_to_cache_unavailable(op: str):
    method = {"get": "get", "set": "set", "take": "getdel", "delete": "delete"}[op]
    client = _mock_client(**{method: AsyncMock(side_effect=RedisError("offline"))})
    cache = RedisCache(client, namespace="ns")
    args = {"get": ("k",), "set": ("k", "v", 5), "take": ("k",), "delete": ("k",)}[op]
    with pytest.raises(CacheUnavailableError):
        await getattr(cache, op)(*args)


async def test_close_closes_the_client():
    client = _mock_client()
    await RedisCache(client, namespace="ns").close()
    client.aclose.assert_awaited_once()
