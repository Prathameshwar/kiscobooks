from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from billing_platform.cache import RedisCache, RedisError
from pydantic import TypeAdapter
from sqlalchemy import select

from identity.models import Country, ReferenceCacheGeneration, ReferenceSyncState
from identity.services.reference_cache import ReferenceChoiceCache
from identity.services.tenant_choices import RegistrationChoices, registration_choices

pytest_plugins = ["tests.test_platform_setup"]


@pytest.fixture
def reference_cache(setup_app):
    app, _, _ = setup_app
    values = {}

    async def get(key):
        return values.get(key)

    async def put(key, value, *, ex):
        assert 1 <= ex <= 3600
        values[key] = value

    redis = SimpleNamespace(get=AsyncMock(side_effect=get), set=AsyncMock(side_effect=put))
    cache = ReferenceChoiceCache(RedisCache(redis, namespace="test:reference"), ttl_seconds=300)
    app.state.reference_cache = cache
    return cache, redis, values


async def test_registration_cache_hit_skips_catalogue_queries_and_keeps_rate_limit(
    setup_app, reference_cache, client, engine
):
    from sqlalchemy import event

    queries = []

    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        first = await client.get("/v1/registration/options")
        assert first.status_code == 200
        queries.clear()
        second = await client.get("/v1/registration/options")
        assert second.json() == first.json()
        assert second.headers["Cache-Control"] == "no-store"
        assert len(queries) == 1 and "reference_cache_generation" in queries[0]
        assert reference_cache[1].set.await_count == 1
        app, _, _ = setup_app
        app.state.auth_limiter = Mock()
        app.state.auth_limiter.allow.return_value = False
        assert (await client.get("/v1/registration/options")).status_code == 429
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def test_edit_archive_and_rollback_invalidate_transactionally(
    reference_cache, client, factory
):
    before = (await client.get("/v1/registration/options")).json()
    async with factory() as db:
        country = await db.get(Country, "IN")
        country.name = "Rolled back"
        await db.flush()
        await db.rollback()
    assert (await client.get("/v1/registration/options")).json() == before
    assert reference_cache[1].set.await_count == 1
    async with factory() as db, db.begin():
        country = await db.get(Country, "IN")
        country.name = "India updated"
    assert (await client.get("/v1/registration/options")).json()["countries"] == [
        {"code": "IN", "name": "India updated"}
    ]
    async with factory() as db, db.begin():
        country = await db.get(Country, "IN")
        country.is_active = False
    assert (await client.get("/v1/registration/options")).json() == {"countries": [], "states": []}
    assert reference_cache[1].set.await_count == 3


async def test_acknowledgement_advances_generation_but_noop_does_not(
    reference_cache, client, factory
):
    await client.get("/v1/registration/options")
    async with factory() as db, db.begin():
        initial = await db.scalar(select(ReferenceCacheGeneration.token))
        db.add(ReferenceSyncState(service="catalog"))
    async with factory() as db, db.begin():
        changed = await db.scalar(select(ReferenceCacheGeneration.token))
        assert changed != initial
        country = await db.get(Country, "IN")
        country.name = country.name
    async with factory() as db:
        assert await db.scalar(select(ReferenceCacheGeneration.token)) == changed


@pytest.mark.parametrize(
    "failure", ["read", "write", "corrupt", "wrong_schema", "oversized", "encoding"]
)
async def test_cache_failures_fall_back_without_changing_response(reference_cache, client, failure):
    cache, redis, values = reference_cache
    baseline = await client.get("/v1/registration/options")
    if failure == "read":
        redis.get.side_effect = RedisError("unavailable")
    elif failure == "encoding":
        redis.get.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
    elif failure == "write":
        values.clear()
        redis.set.side_effect = RedisError("unavailable")
    else:
        replacement = {
            "corrupt": "{invalid",
            "wrong_schema": '{"countries": [], "states": [], "secret": "invalid"}',
            "oversized": " " * (cache.maximum_bytes + 1),
        }[failure]
        for key in values:
            values[key] = replacement
    response = await client.get("/v1/registration/options")
    assert response.status_code == 200 and response.json() == baseline.json()


async def test_generation_change_during_load_never_publishes_mixed_projection(
    reference_cache, factory
):
    cache, redis, _ = reference_cache
    async with factory() as db:

        async def racing_loader():
            value = await registration_choices(db)
            country = await db.get(Country, "IN")
            country.name = "Changed during load"
            await db.flush()
            return value

        await cache.resolve(db, "registration", TypeAdapter(RegistrationChoices), racing_loader)
        assert redis.set.await_count == 0
        await db.rollback()


async def test_disabled_cache_and_pending_changes_use_database(reference_cache, factory):
    cache, redis, _ = reference_cache
    async with factory() as db:
        country = await db.get(Country, "IN")
        country.name = "Uncommitted"
        await cache.resolve(
            db, "registration", TypeAdapter(RegistrationChoices), lambda: registration_choices(db)
        )
        assert redis.get.await_count == 0
        await db.rollback()
    disabled = ReferenceChoiceCache(cache.cache, ttl_seconds=0)
    async with factory() as db:
        await disabled.resolve(
            db, "registration", TypeAdapter(RegistrationChoices), lambda: registration_choices(db)
        )
    assert redis.get.await_count == 0


async def test_cached_pending_references_wait_for_both_delivery_acknowledgements(
    setup_app, reference_cache, client, factory
):
    from tests.test_reference_replication import (
        test_pending_custom_choices_wait_for_both_consumer_acks,
    )

    await test_pending_custom_choices_wait_for_both_consumer_acks(setup_app, client, factory)
    assert reference_cache[1].set.await_count >= 3


async def test_cached_platform_options_recheck_live_user_status(
    setup_app, reference_cache, client, factory
):
    import uuid

    from billing_platform.db import tenant_scope

    from identity.models import User
    from tests.test_platform_setup import signed
    from tests.test_reference_crud import ready

    key, result = await ready(setup_app, client, factory)
    for path in ("/v1/platform/tenant-options", "/v1/platform/references/options"):
        assert (await client.get(path, headers=signed(key))).status_code == 200
        assert (await client.get(path, headers=signed(key))).status_code == 200
    reads = reference_cache[1].get.await_count
    with tenant_scope(uuid.UUID(result["tenant_id"])):
        async with factory() as db, db.begin():
            user = await db.get(User, uuid.UUID(result["administrator_id"]))
            user.status = "inactive"
    for path in ("/v1/platform/tenant-options", "/v1/platform/references/options"):
        assert (await client.get(path, headers=signed(key))).status_code in (401, 403)
    assert reference_cache[1].get.await_count == reads


async def test_country_specific_state_keys_do_not_collide(reference_cache, factory):
    from identity.models import State
    from identity.services.company_choices import states

    async with factory() as db, db.begin():
        db.add(
            State(
                code="IN-MH",
                country_code="IN",
                name="Maharashtra",
                subdivision_type="State",
                is_active=True,
            )
        )
    cache, _, _ = reference_cache
    async with factory() as db:
        india = await states(db, "IN", cache)
        other = await states(db, "ZZ", cache)
        assert len(india) == 1 and other == []
        assert await states(db, "IN", cache) == india


def test_cache_namespace_isolates_database_and_ttl_is_bounded(reference_cache):
    from identity.services.reference_cache import namespace

    assert namespace("mysql+asyncmy://localhost/one") != namespace("mysql+asyncmy://localhost/two")
    for invalid in (True, -1, 3601, 1.5):
        with pytest.raises(ValueError):
            ReferenceChoiceCache(reference_cache[0].cache, ttl_seconds=invalid)


def test_reference_cache_ttl_environment_can_start_service(monkeypatch):
    import secrets

    from pydantic import SecretStr, ValidationError

    from identity.config import Settings

    values = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "actor_signing_secret": SecretStr(secrets.token_hex(32)),
        "cursor_signing_secret": SecretStr(secrets.token_hex(32)),
    }
    for accepted in ("0", "300", "3600"):
        monkeypatch.setenv("IDENTITY_REFERENCE_CACHE_TTL_SECONDS", accepted)
        assert Settings(**values).reference_cache_ttl_seconds == int(accepted)
    for rejected in ("-1", "3601", "true", "3.5"):
        monkeypatch.setenv("IDENTITY_REFERENCE_CACHE_TTL_SECONDS", rejected)
        with pytest.raises(ValidationError):
            Settings(**values)


async def test_seed_changes_invalidate_and_identical_seed_preserves_cache(
    reference_cache, client, factory, monkeypatch
):
    from billing_platform.reference import seed

    before = (await client.get("/v1/registration/options")).json()
    async with factory() as db:
        country = await db.get(Country, "IN")
        values = {
            column.name: getattr(country, column.name) for column in Country.__table__.columns
        }
    values["name"] = "Updated seeded name"
    monkeypatch.setattr(seed, "load", lambda name: [values])
    async with factory() as db, db.begin():
        outcome = await seed.seed_reference(db, datasets=("country",), managed=False)
        assert outcome[0].changed
    changed = (await client.get("/v1/registration/options")).json()
    assert changed != before and changed["countries"][0]["name"] == "Updated seeded name"
    writes = reference_cache[1].set.await_count
    async with factory() as db, db.begin():
        outcome = await seed.seed_reference(db, datasets=("country",), managed=False)
        assert not outcome[0].changed
    assert (await client.get("/v1/registration/options")).json() == changed
    assert reference_cache[1].set.await_count == writes
