"""Versioned, permission-safe company display projection caching."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from billing_platform.cache import RedisCache
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from redis.exceptions import RedisError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from identity.domain.field_registry import COMPANY_ENTITY_TYPE
from identity.models import Company, User
from identity.services.company_display_cache import CompanyDisplayCache, display_key, namespace
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_field_policy, build_user, seed_two_companies

TENANT = uuid7()
COMPANY = uuid7()
USER = uuid7()


def _client(**overrides: object) -> SimpleNamespace:
    base = {"get": AsyncMock(return_value=None), "set": AsyncMock()}
    base.update(overrides)
    return SimpleNamespace(**base)


def _key(
    *,
    tenant_id: uuid.UUID = TENANT,
    company_id: uuid.UUID = COMPANY,
    user_id: uuid.UUID = USER,
    access: str = "access-a",
    company_second: int = 0,
    user_second: int = 0,
) -> str:
    return display_key(
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        company_version=dt.datetime(2026, 11, 1, 6, 0, company_second, tzinfo=dt.UTC),
        user_version=dt.datetime(2026, 11, 1, 6, 1, user_second, tzinfo=dt.UTC),
        access_fingerprint=access,
    )


def _value() -> dict[str, object]:
    return {
        "timezone": "Asia/Kolkata",
        "currency_display": "symbol",
        "base_currency": "INR",
        "amount_precision": 2,
        "quantity_precision": 3,
        "rounding_mode": "half_up",
        "locale": "en-IN",
        "date_format": "dd-MM-yyyy",
        "datetime_format": "dd-MM-yyyy HH:mm",
        "digit_grouping": "indian",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "negative_format": "minus",
        "currency_symbol_position": "prefix",
        "currency_symbol_override": None,
        "show_amount_in_words": True,
    }


@pytest.mark.asyncio
async def test_miss_populates_and_hit_skips_authoritative_loader() -> None:
    values: dict[str, str] = {}

    async def get(key: str) -> str | None:
        return values.get(key)

    async def put(key: str, value: str, *, ex: int) -> None:
        assert ex == 300
        values[key] = value

    redis = _client(get=AsyncMock(side_effect=get), set=AsyncMock(side_effect=put))
    cache = CompanyDisplayCache(RedisCache(redis, namespace="test:display"), ttl_seconds=300)
    loader = AsyncMock(return_value=_value())
    key = _key()

    assert await cache.resolve(key, loader) == _value()
    assert await cache.resolve(key, loader) == _value()
    loader.assert_awaited_once()
    assert cache.outcomes == {"miss": 1, "fill": 1, "hit": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "read",
        "write",
        "encoding",
        "malformed",
        "unknown",
        "non_object",
        "invalid_type",
        "oversized",
        "deep",
        "surrogate",
    ],
)
async def test_failure_or_untrusted_payload_falls_back(failure: str) -> None:
    value = {
        "malformed": "{bad",
        "unknown": '{"secret":"not-a-display-field"}',
        "non_object": "[]",
        "invalid_type": '{"amount_precision":"2"}',
        "oversized": " " * (CompanyDisplayCache.maximum_bytes + 1),
        "deep": '{"date_format":' + "[" * 6000 + "0" + "]" * 6000 + "}",
        "surrogate": '{"date_format":"\\ud800"}',
    }.get(failure)
    redis = _client(get=AsyncMock(return_value=value))
    if failure == "read":
        redis.get.side_effect = RedisError("unavailable")
    if failure == "write":
        redis.set.side_effect = RedisError("unavailable")
    if failure == "encoding":
        redis.get.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
    cache = CompanyDisplayCache(RedisCache(redis, namespace="test:display"), ttl_seconds=300)
    loader = AsyncMock(return_value=_value())

    assert await cache.resolve(_key(), loader) == _value()
    loader.assert_awaited_once()
    assert cache.outcomes.get("fallback", 0) == 1


def test_versions_access_and_database_namespaces_cannot_collide() -> None:
    baseline = _key()
    assert baseline != _key(tenant_id=uuid7())
    assert baseline != _key(company_id=uuid7())
    assert baseline != _key(user_id=uuid7())
    assert baseline != _key(access="access-b")
    assert baseline != _key(company_second=1)
    assert baseline != _key(user_second=1)
    assert namespace("mysql+asyncmy://localhost/one") != namespace("mysql+asyncmy://localhost/two")


def test_ttl_is_bounded() -> None:
    redis = RedisCache(_client(), namespace="test:display")
    for invalid in (True, -1, 3601, 1.5):
        with pytest.raises(ValueError):
            # Deliberately pass invalid types to exercise runtime configuration boundaries.
            CompanyDisplayCache(redis, ttl_seconds=invalid)  # type: ignore[arg-type]


@pytest.fixture
def display_cache(app: FastAPI) -> tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]]:
    values: dict[str, str] = {}

    async def get(key: str) -> str | None:
        return values.get(key)

    async def put(key: str, value: str, *, ex: int) -> None:
        assert ex == 300
        values[key] = value

    redis = _client(get=AsyncMock(side_effect=get), set=AsyncMock(side_effect=put))
    cache = CompanyDisplayCache(RedisCache(redis, namespace="test:display"), ttl_seconds=300)
    app.state.company_display_cache = cache
    return cache, redis, values


def _headers(tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant_id,
        user_id=user_id,
        grants=[grant(["company.read"], scope_type="company", scope_id=company_id)],
    )


@pytest.mark.asyncio
async def test_endpoint_hit_skips_authoritative_company_and_user_loads(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    engine: AsyncEngine,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=user_id, locale="mr-IN"))
        await session.commit()
    from identity.services import display

    resolve = Mock(wraps=display.resolve_display)
    monkeypatch.setattr(display, "resolve_display", resolve)
    statements: list[str] = []

    def capture(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        first = await client.get(
            f"/v1/companies/{company_id}/display-config",
            headers=_headers(tenant_a, user_id, company_id),
        )
        assert any("company.amount_precision" in sql for sql in statements)
        statements.clear()
        second = await client.get(
            f"/v1/companies/{company_id}/display-config",
            headers=_headers(tenant_a, user_id, company_id),
        )
        assert any("company.updated_at" in sql and "user.updated_at" in sql for sql in statements)
        assert not any(
            "company.amount_precision" in sql or "user.locale" in sql for sql in statements
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert second.json()["locale"] == "mr-IN"
    resolve.assert_called_once()
    assert display_cache[1].get.await_count == 2
    assert display_cache[1].set.await_count == 1


@pytest.mark.asyncio
async def test_cache_miss_uses_fresh_sources_even_if_request_preloaded_old_rows(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=user_id, date_format="dd-MM-yyyy"))
        await session.commit()
    from identity.api.dependencies import session as session_dependency

    async def preloaded_session() -> AsyncIterator[AsyncSession]:
        with tenant_scope(tenant_a):
            async with factory() as request_db:
                old_company = await request_db.get(Company, company_id)
                old_user = await request_db.get(User, user_id)
                assert old_company is not None and old_user is not None
                await request_db.commit()
                async with factory() as updater:
                    company = await updater.get(Company, company_id)
                    user = await updater.get(User, user_id)
                    assert company is not None and user is not None
                    company.amount_precision = 4
                    user.date_format = "yyyy-MM-dd"
                    await updater.commit()
                # Keep the old objects alive, as authentication can do during a request.
                assert old_company.amount_precision == 2
                assert old_user.date_format == "dd-MM-yyyy"
                yield request_db

    app.dependency_overrides[session_dependency] = preloaded_session
    try:
        first = await client.get(
            f"/v1/companies/{company_id}/display-config",
            headers=_headers(tenant_a, user_id, company_id),
        )
    finally:
        app.dependency_overrides.pop(session_dependency)
    assert first.status_code == 200
    assert first.json()["amount_precision"] == 4
    assert first.json()["date_format"] == "yyyy-MM-dd"
    second = await client.get(
        f"/v1/companies/{company_id}/display-config",
        headers=_headers(tenant_a, user_id, company_id),
    )
    assert second.json() == first.json()
    assert display_cache[0].outcomes == {"miss": 1, "fill": 1, "hit": 1}


@pytest.mark.asyncio
async def test_committed_company_user_and_policy_versions_never_reuse_stale_projection(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=user_id))
        await session.commit()
    headers = _headers(tenant_a, user_id, company_id)
    path = f"/v1/companies/{company_id}/display-config"

    assert (await client.get(path, headers=headers)).json()["date_format"] == "dd-MM-yyyy"
    writes = display_cache[1].set.await_count
    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        assert company is not None
        company.date_format = "rolled-back-format"
        await session.flush()
        await session.rollback()
    assert (await client.get(path, headers=headers)).json()["date_format"] == "dd-MM-yyyy"
    assert display_cache[1].set.await_count == writes

    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        assert company is not None
        company.date_format = "yyyy-MM-dd"
        await session.commit()
    assert (await client.get(path, headers=headers)).json()["date_format"] == "yyyy-MM-dd"

    with tenant_scope(tenant_a):
        user = await session.get(User, user_id)
        assert user is not None
        user.date_format = "MM/dd/yyyy"
        await session.commit()
    assert (await client.get(path, headers=headers)).json()["date_format"] == "MM/dd/yyyy"

    with tenant_scope(tenant_a):
        policy = build_field_policy(
            tenant_id=tenant_a,
            subject_id=user_id,
            subject_type="user",
            entity_type=COMPANY_ENTITY_TYPE,
            field_key="date_format",
            access="read",
            scope_type="company",
            scope_id=company_id,
        )
        session.add(policy)
        await session.commit()
    assert "date_format" not in (await client.get(path, headers=headers)).json()
    assert display_cache[1].set.await_count == 4
    # Even schema-valid corruption must not put a denied field back in a response.
    protected_key = next(reversed(display_cache[2]))
    corrupted = json.loads(display_cache[2][protected_key]) | {"date_format": "MM/dd/yyyy"}
    display_cache[2][protected_key] = json.dumps(corrupted)
    assert "date_format" not in (await client.get(path, headers=headers)).json()


@pytest.mark.asyncio
async def test_refused_company_scope_never_reads_or_populates_cache(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    allowed = uuid7()
    user_id = uuid7()
    response = await client.get(
        f"/v1/companies/{company_id}/display-config",
        headers=_headers(tenant_a, user_id, allowed),
    )
    assert response.status_code == 403
    display_cache[1].get.assert_not_awaited()
    display_cache[1].set.assert_not_awaited()


@pytest.mark.asyncio
async def test_endpoint_redis_outage_preserves_authoritative_response(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=user_id, locale="mr-IN"))
        await session.commit()
    display_cache[1].get.side_effect = RedisError("unavailable")
    display_cache[1].set.side_effect = RedisError("unavailable")

    response = await client.get(
        f"/v1/companies/{company_id}/display-config",
        headers=_headers(tenant_a, user_id, company_id),
    )
    assert response.status_code == 200
    assert response.json()["locale"] == "mr-IN"
    assert display_cache[0].outcomes["fallback"] == 1
    display_cache[1].set.assert_not_awaited()


def test_company_display_cache_ttl_environment_can_disable_or_bound_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import secrets

    from pydantic import SecretStr, ValidationError

    from identity.config import Settings

    values = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "actor_signing_secret": SecretStr(secrets.token_hex(32)),
        "cursor_signing_secret": SecretStr(secrets.token_hex(32)),
    }
    for accepted in ("0", "300", "3600"):
        monkeypatch.setenv("IDENTITY_COMPANY_DISPLAY_CACHE_TTL_SECONDS", accepted)
        assert Settings(**values).company_display_cache_ttl_seconds == int(accepted)
    for rejected in ("-1", "3601", "true", "3.5"):
        monkeypatch.setenv("IDENTITY_COMPANY_DISPLAY_CACHE_TTL_SECONDS", rejected)
        with pytest.raises(ValidationError):
            Settings(**values)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("TEST_IDENTITY_REDIS_URL"),
    reason="TEST_IDENTITY_REDIS_URL is required for the isolated native Redis check",
)
async def test_native_redis_round_trip_uses_ttl_and_removes_only_its_key() -> None:
    from billing_platform.cache import create_redis_client

    redis = create_redis_client(os.environ["TEST_IDENTITY_REDIS_URL"])
    cache_namespace = "test:company-display:" + uuid.uuid4().hex
    cache = CompanyDisplayCache(RedisCache(redis, namespace=cache_namespace), ttl_seconds=30)
    key = _key()
    loader = AsyncMock(return_value=_value())
    try:
        assert await cache.resolve(key, loader) == _value()
        assert await cache.resolve(key, loader) == _value()
        loader.assert_awaited_once()
        ttl = await redis.ttl(f"{cache_namespace}:{key}")
        assert 1 <= ttl <= 30
    finally:
        await redis.delete(f"{cache_namespace}:{key}")
        await redis.aclose()


@pytest.mark.asyncio
async def test_conditional_policy_uses_live_company_fields_before_cache_lookup(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_id=user_id,
                subject_type="user",
                entity_type=COMPANY_ENTITY_TYPE,
                field_key="date_format",
                access="read",
                scope_type="company",
                scope_id=company_id,
                condition={"field": "amount_precision", "cmp": "gte", "value": "3"},
            )
        )
        await session.commit()
    path = f"/v1/companies/{company_id}/display-config"
    headers = _headers(tenant_a, user_id, company_id)
    assert "date_format" in (await client.get(path, headers=headers)).json()
    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        assert company is not None
        company.amount_precision = 4
        await session.commit()
    assert "date_format" not in (await client.get(path, headers=headers)).json()
    protected_key = next(reversed(display_cache[2]))
    display_cache[2][protected_key] = json.dumps(
        json.loads(display_cache[2][protected_key]) | {"date_format": "MM/dd/yyyy"}
    )
    assert "date_format" not in (await client.get(path, headers=headers)).json()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["anonymous", "unpermitted", "foreign", "missing", "invalid"])
async def test_refused_or_missing_source_never_reads_the_cache(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    case: str,
) -> None:
    company_id, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    target = {"foreign": foreign, "missing": uuid7(), "invalid": "invalid-uuid"}.get(
        case, company_id
    )
    headers = _headers(tenant_a, user_id, target if isinstance(target, uuid.UUID) else company_id)
    if case == "anonymous":
        headers = {}
    elif case == "unpermitted":
        headers = actor_headers(tenant_id=tenant_a, user_id=user_id)
    response = await client.get(f"/v1/companies/{target}/display-config", headers=headers)
    assert response.status_code == {"anonymous": 401, "unpermitted": 403, "invalid": 422}.get(
        case, 404
    )
    display_cache[1].get.assert_not_awaited()
    display_cache[1].set.assert_not_awaited()


@pytest.mark.asyncio
async def test_warmed_cache_keeps_company_user_and_current_authority_isolated(
    display_cache: tuple[CompanyDisplayCache, SimpleNamespace, dict[str, str]],
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    first_user, second_user = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        other = build_company(tenant_id=tenant_a, code="OTHER", amount_precision=4)
        session.add_all(
            [
                other,
                build_user(tenant_id=tenant_a, user_id=first_user, date_format="yyyy-MM-dd"),
                build_user(
                    tenant_id=tenant_a,
                    user_id=second_user,
                    email="other@example.test",
                    date_format="MM/dd/yyyy",
                ),
            ]
        )
        await session.commit()
        other_id = other.id
    for target, user, precision, date_format in (
        (company_id, first_user, 2, "yyyy-MM-dd"),
        (company_id, second_user, 2, "MM/dd/yyyy"),
        (other_id, first_user, 4, "yyyy-MM-dd"),
        (company_id, first_user, 2, "yyyy-MM-dd"),
    ):
        response = await client.get(
            f"/v1/companies/{target}/display-config",
            headers=_headers(tenant_a, user, target),
        )
        assert response.status_code == 200
        assert response.json()["amount_precision"] == precision
        assert response.json()["date_format"] == date_format
    reads = display_cache[1].get.await_count
    response = await client.get(
        f"/v1/companies/{company_id}/display-config",
        headers=actor_headers(tenant_id=tenant_a, user_id=first_user),
    )
    assert response.status_code == 403
    assert display_cache[1].get.await_count == reads
    assert display_cache[0].outcomes == {"miss": 3, "fill": 3, "hit": 1}


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("TEST_IDENTITY_REDIS_URL"), reason="TEST_IDENTITY_REDIS_URL is required"
)
@pytest.mark.parametrize("payload", [b"\xff", b"{bad", b'{"date_format":"\\ud800"}', b" " * 16_385])
async def test_native_redis_corruption_falls_back(payload: bytes) -> None:
    from billing_platform.cache import create_redis_client

    redis = create_redis_client(os.environ["TEST_IDENTITY_REDIS_URL"])
    cache_namespace = "test:company-display:" + uuid.uuid4().hex
    cache = CompanyDisplayCache(RedisCache(redis, namespace=cache_namespace))
    key = _key()
    scoped_key = f"{cache_namespace}:{key}"
    loader = AsyncMock(return_value=_value())
    try:
        await redis.set(scoped_key, payload, ex=30)
        assert await cache.resolve(key, loader) == _value()
        loader.assert_awaited_once()
        assert cache.outcomes["fallback"] == 1
    finally:
        await redis.delete(scoped_key)
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("TEST_IDENTITY_REDIS_URL"), reason="TEST_IDENTITY_REDIS_URL is required"
)
async def test_native_redis_expiry_reloads_authoritative_values() -> None:
    from billing_platform.cache import create_redis_client

    redis = create_redis_client(os.environ["TEST_IDENTITY_REDIS_URL"])
    cache_namespace = "test:company-display:" + uuid.uuid4().hex
    cache = CompanyDisplayCache(RedisCache(redis, namespace=cache_namespace), ttl_seconds=1)
    key = _key()
    loader = AsyncMock(return_value=_value())
    try:
        assert await cache.resolve(key, loader) == _value()
        await asyncio.sleep(1.1)
        updated = _value() | {"date_format": "yyyy-MM-dd"}
        loader.return_value = updated
        assert await cache.resolve(key, loader) == updated
        assert loader.await_count == 2
    finally:
        await redis.delete(f"{cache_namespace}:{key}")
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [True, False])
async def test_disabled_or_unconfigured_display_cache_keeps_other_caches(
    app: FastAPI, configured: bool
) -> None:
    from pydantic import SecretStr

    from identity.main import create_app

    settings = app.state.settings.model_copy(
        update={
            "redis_url": SecretStr("redis://127.0.0.1:6379/0") if configured else None,
            "company_display_cache_ttl_seconds": 0,
        }
    )
    application = create_app(settings)
    try:
        assert application.state.company_display_cache is None
        assert (application.state.grant_cache is not None) == configured
        assert (application.state.reference_cache is not None) == configured
    finally:
        if application.state.redis is not None:
            await application.state.redis.aclose()
        await application.state.engine.dispose()
