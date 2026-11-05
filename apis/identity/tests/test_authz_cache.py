"""The permission-resolution cache — read-through, fail-open, and invalidation.

The invariant under test is the one CLAUDE.md §5.4 turns on: grants are cached, but a
cache outage or a poisoned entry must fall back to a live resolution and *never* widen
access or 5xx the request. No live Redis and no database: the Redis client is a mock
(the pattern the step-up adapter test uses) and ``live_grants`` is stubbed, so this
exercises the cache's control flow in isolation.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.authz import Grant, Scope, encode_grants
from billing_platform.cache import RedisCache
from billing_platform.constants import SCOPE_ALL
from billing_platform.ids import uuid7
from redis.exceptions import RedisError

from identity.api.dependencies import _run_after_commit
from identity.services import authz_cache
from identity.services.authz_cache import GrantCache

TENANT = uuid7()
USER = uuid7()
GROUP = uuid7()
GRANTS = (
    Grant(frozenset({"company.read"}), Scope("tenant", SCOPE_ALL), dt.date(2026, 4, 1), None, True),
)
GROUPS = frozenset({GROUP})


def _client(**overrides: object) -> SimpleNamespace:
    base = {
        "get": AsyncMock(return_value=None),
        "set": AsyncMock(),
        "getdel": AsyncMock(return_value=None),
        "delete": AsyncMock(),
        "aclose": AsyncMock(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _cache(client: SimpleNamespace) -> GrantCache:
    return GrantCache(RedisCache(client, namespace="identity:authz"), ttl_seconds=30)


@pytest.fixture(autouse=True)
def _stub_live_grants(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Every test resolves through this stub rather than the database."""
    loader = AsyncMock(return_value=(GRANTS, GROUPS))
    monkeypatch.setattr(authz_cache, "live_grants", loader)
    return loader


async def test_miss_resolves_from_db_and_populates(_stub_live_grants: AsyncMock):
    client = _client(get=AsyncMock(return_value=None))
    grants, groups = await _cache(client).resolve(db=object(), tenant_id=TENANT, user_id=USER)  # type: ignore[arg-type]
    assert grants == GRANTS
    assert groups == GROUPS
    _stub_live_grants.assert_awaited_once()
    # The resolved set was written back under the tenant:user key with the TTL.
    client.set.assert_awaited_once()
    assert client.set.await_args.args[0] == f"identity:authz:{TENANT}:{USER}"
    assert client.set.await_args.kwargs["ex"] == 30


async def test_hit_returns_cached_without_touching_the_database(_stub_live_grants: AsyncMock):
    client = _client(get=AsyncMock(return_value=encode_grants(GRANTS, GROUPS)))
    grants, groups = await _cache(client).resolve(db=object(), tenant_id=TENANT, user_id=USER)  # type: ignore[arg-type]
    assert grants == GRANTS
    assert groups == GROUPS
    _stub_live_grants.assert_not_awaited()
    client.set.assert_not_awaited()


async def test_redis_outage_falls_back_to_db(_stub_live_grants: AsyncMock):
    # get() raises -> read is fail-open; set() also raises -> populate is best-effort.
    client = _client(
        get=AsyncMock(side_effect=RedisError("down")),
        set=AsyncMock(side_effect=RedisError("down")),
    )
    grants, groups = await _cache(client).resolve(db=object(), tenant_id=TENANT, user_id=USER)  # type: ignore[arg-type]
    assert grants == GRANTS  # the request still authorizes on live data
    _stub_live_grants.assert_awaited_once()


async def test_poisoned_entry_is_treated_as_a_miss(_stub_live_grants: AsyncMock):
    client = _client(get=AsyncMock(return_value="{not valid json"))
    grants, _ = await _cache(client).resolve(db=object(), tenant_id=TENANT, user_id=USER)  # type: ignore[arg-type]
    assert grants == GRANTS
    _stub_live_grants.assert_awaited_once()  # re-resolved rather than trusting garbage


async def test_invalidate_deletes_the_user_key():
    client = _client()
    await _cache(client).invalidate(TENANT, USER)
    client.delete.assert_awaited_once_with(f"identity:authz:{TENANT}:{USER}")


async def test_invalidate_is_silent_on_outage(caplog):
    client = _client(delete=AsyncMock(side_effect=RedisError("down")))
    # TTL is the backstop: a failed delete must not raise into a committed write.
    await _cache(client).invalidate(TENANT, USER)
    assert "permission cache invalidation failed" in caplog.text
    assert str(USER) not in caplog.text


async def test_schedule_invalidation_defers_to_after_commit():
    client = _client()
    cache = _cache(client)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(grant_cache=cache)),
        state=SimpleNamespace(),
    )
    authz_cache.schedule_invalidation(request, TENANT, USER)  # type: ignore[arg-type]
    hooks = request.state.after_commit
    assert len(hooks) == 1
    client.delete.assert_not_awaited()  # not until the hook runs
    await hooks[0]()
    client.delete.assert_awaited_once_with(f"identity:authz:{TENANT}:{USER}")


async def test_schedule_invalidation_is_a_noop_without_a_cache():
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(grant_cache=None)),
        state=SimpleNamespace(),
    )
    authz_cache.schedule_invalidation(request, TENANT, USER)  # type: ignore[arg-type]
    assert not hasattr(request.state, "after_commit")


async def test_failed_post_commit_hook_is_logged_without_failing_committed_write(caplog):
    async def fail():
        raise RuntimeError("sensitive connection detail")

    request = SimpleNamespace(state=SimpleNamespace(after_commit=[fail]))
    await _run_after_commit(request)  # type: ignore[arg-type] # minimal request state
    assert "post-commit hook failed: RuntimeError" in caplog.text
    assert "sensitive connection detail" not in caplog.text
