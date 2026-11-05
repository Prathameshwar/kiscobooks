from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.custom_fields import CustomFieldValueIndex
from catalog.models.field_indexes import FieldIndexState, FieldRebuildJob
from catalog.tasks.index_rebuilds import build_chunk, cleanup_chunk, permissions
from tests.test_actor_authorization import proof
from tests.test_api import headers
from tests.test_classification_api import create, setup_source
from tests.test_options import custom_facts

ENTITY = "catalog.item_group"
KEY = "cf_note"


def path(company: uuid.UUID) -> str:
    return f"/v1/companies/{company}/entities/{ENTITY}/field-indexes/{KEY}"


def filter_query(value: str | None = None) -> dict[str, str]:
    return {
        "custom_filters": json.dumps(
            [
                {
                    "key": KEY,
                    "operator": "is_set" if value is None else "eq",
                    "value": True if value is None else value,
                }
            ]
        )
    }


async def setup(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
) -> tuple[dict[str, str], list[dict[str, Any]], tuple[SnapshotRecord, ...]]:
    facts = custom_facts(company, user)
    await setup_source(factory, tenant, company, user, facts=facts)
    auth = headers(company, permission=sorted(permissions(ENTITY)), tenant=tenant, user=user)
    rows = []
    for code, value in (("A", "alpha"), ("B", "beta")):
        response = await create(
            client,
            company,
            auth,
            "item-groups",
            {"code": code, "name": code, "valid_from": "2020-01-01", "custom_fields": {KEY: value}},
        )
        assert response.status_code == 201, response.text
        rows.append(response.json())
    searchable = tuple(
        row.model_copy(update={"data": {**row.data, "is_searchable": True}})
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    await setup_source(factory, tenant, company, user, facts=searchable, version=3)
    return auth, rows, searchable


async def start(
    client: httpx.AsyncClient, company: uuid.UUID, auth: dict[str, str], version: int = 0
) -> dict[str, Any]:
    response = await client.post(
        path(company) + "/rebuilds",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": version},
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def chunk(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    job: dict[str, Any],
    *,
    limit: int = 25,
    version: int = 3,
) -> dict[str, Any]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            result = await build_chunk(
                db,
                proof(
                    tenant, company, user, source_version=version, permissions=permissions(ENTITY)
                ),
                company=company,
                entity=ENTITY,
                key=KEY,
                job_id=uuid.UUID(job["id"]),
                limit=limit,
            )
            return result.model_dump(mode="json")


async def test_online_backfill_dual_writes_cursor_and_retired_cleanup(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user = uuid7(), uuid7()
    auth, rows, _ = await setup(client, factory, tenant_a, company, user)
    listing = f"/v1/companies/{company}/item-groups"
    assert (await client.get(listing, params=filter_query(), headers=auth)).status_code == 409
    assert (await client.get(path(company), headers=auth)).json()["row_version"] == 0
    job = await start(client, company, auth)
    assert job["status"] == "pending" and "definition" not in job
    first = await chunk(factory, tenant_a, company, user, job, limit=1)
    assert first["status"] == "running" and first["processed_count"] == 1
    assert (await client.get(listing, params=filter_query(), headers=auth)).status_code == 409
    updated = await client.patch(
        listing + "/" + rows[0]["id"],
        json={"expected_version": 1, "custom_fields": {KEY: "changed"}},
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert updated.status_code == 200, updated.text
    # A commit behind the UUID traversal cursor reaches the build through dual write.
    with monkeypatch.context() as patch:
        patch.setattr(
            "catalog.tasks.classification.uuid7",
            lambda: uuid.UUID("00000000-0001-7000-8000-000000000001"),
        )
        behind = await create(
            client,
            company,
            auth,
            "item-groups",
            {"code": "C", "name": "C", "valid_from": "2020-01-01", "custom_fields": {KEY: "gamma"}},
        )
        assert behind.status_code == 201, behind.text
    completed = await chunk(factory, tenant_a, company, user, job)
    assert completed["status"] == "succeeded" and completed["processed_count"] == 2
    result = await client.get(listing, params=filter_query(), headers=auth)
    assert result.status_code == 200, result.text
    assert [row["code"] for row in result.json()["items"]] == ["A", "B", "C"]
    assert (await client.get(listing, params=filter_query("changed"), headers=auth)).json()[
        "items"
    ][0]["id"] == rows[0]["id"]
    page = (await client.get(listing, params={**filter_query(), "limit": 1}, headers=auth)).json()
    state = (await client.get(path(company), headers=auth)).json()
    second = await start(client, company, auth, state["row_version"])
    assert (await client.get(listing, params=filter_query(), headers=auth)).status_code == 200
    final = await chunk(factory, tenant_a, company, user, second)
    assert final["phase"] == "cleanup"
    assert (
        await client.get(
            listing,
            params={**filter_query(), "limit": 1, "cursor": page["page"]["next_cursor"]},
            headers=auth,
        )
    ).status_code == 422
    with tenant_scope(tenant_a):
        for _ in range(6):
            async with factory.begin() as db:
                cleaned = await cleanup_chunk(
                    db,
                    tenant=tenant_a,
                    company=company,
                    entity=ENTITY,
                    key=KEY,
                    job_id=uuid.UUID(second["id"]),
                    limit=1,
                )
            if cleaned.phase == "complete":
                break
        assert cleaned.phase == "complete" and cleaned.cleanup_count == 3
        async with factory.begin() as db:
            assert (
                await db.scalar(
                    select(func.count(CustomFieldValueIndex.id)).where(
                        CustomFieldValueIndex.generation == 1
                    )
                )
                == 0
            )
    state = (await client.get(path(company), headers=auth)).json()
    assert state["ready_for_current_definition"] is True and state["retired_generation"] is None


async def test_job_api_scope_idempotency_cancel_and_lean_history(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth, _, _ = await setup(client, factory, tenant_a, company, user)
    base = path(company)
    body = {"expected_version": 0}
    assert (await client.post(base + "/rebuilds", json=body)).status_code == 401
    reader = headers(company, permission="item_group.read", tenant=tenant_a, user=user)
    assert (
        await client.post(
            base + "/rebuilds", json=body, headers={**reader, "Idempotency-Key": "denied"}
        )
    ).status_code == 403
    wrong = headers(uuid7(), permission=sorted(permissions(ENTITY)), tenant=tenant_a, user=user)
    assert (
        await client.post(
            base + "/rebuilds", json=body, headers={**wrong, "Idempotency-Key": "wrong"}
        )
    ).status_code == 403
    request_headers = {**auth, "Idempotency-Key": str(uuid7())}
    first = await client.post(base + "/rebuilds", json=body, headers=request_headers)
    assert first.status_code == 201
    repeated = await client.post(base + "/rebuilds", json=body, headers=request_headers)
    assert repeated.json() == first.json() and repeated.headers["Idempotency-Replayed"] == "true"
    assert (
        await client.post(base + "/rebuilds", json={"expected_version": 1}, headers=request_headers)
    ).status_code == 422
    job = first.json()
    assert (await client.get(base + "/rebuilds/" + job["id"], headers=reader)).status_code == 200
    history = await client.get(base + "/rebuilds?status=pending&limit=1", headers=reader)
    assert history.status_code == 200, history.text
    assert "actor_user_id" not in history.json()["items"][0] and "definition" not in history.text
    for suffix in ("?q=abc", "?sort=status", "?unexpected=yes", "?status=unknown"):
        assert (await client.get(base + "/rebuilds" + suffix, headers=reader)).status_code == 422
    assert (await client.get(base + "?unexpected=yes", headers=reader)).status_code == 422
    first_chunk = await chunk(factory, tenant_a, company, user, job, limit=1)
    response = await client.post(
        base + "/rebuilds/" + job["id"] + "/cancel",
        json={"expected_version": first_chunk["row_version"]},
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    with pytest.raises(ConflictError):
        await chunk(factory, tenant_a, company, user, job)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            cleaned = await cleanup_chunk(
                db,
                tenant=tenant_a,
                company=company,
                entity=ENTITY,
                key=KEY,
                job_id=uuid.UUID(job["id"]),
            )
            assert cleaned.phase == "complete" and cleaned.cleanup_count == 1
    assert (
        await client.get(
            f"/v1/companies/{company}/item-groups", params=filter_query(), headers=auth
        )
    ).status_code == 409


async def test_chunk_rollback_and_changed_definition_never_activate(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth, _, facts = await setup(client, factory, tenant_a, company, user)
    job = await start(client, company, auth)
    with tenant_scope(tenant_a):
        async with factory() as db:
            await db.begin()
            before = await db.scalar(select(func.count(Outbox.id)))
            await build_chunk(
                db,
                proof(tenant_a, company, user, source_version=3, permissions=permissions(ENTITY)),
                company=company,
                entity=ENTITY,
                key=KEY,
                job_id=uuid.UUID(job["id"]),
                limit=1,
            )
            await db.rollback()
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == before
            row = await db.get(FieldRebuildJob, uuid.UUID(job["id"]))
            assert row is not None and row.checkpoint_id is None and row.processed_count == 0
            assert await db.scalar(select(func.count(CustomFieldValueIndex.id))) == 0
    changed = tuple(
        row.model_copy(update={"data": {**row.data, "validation": {"max_length": 2}}})
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    await setup_source(factory, tenant_a, company, user, facts=changed, version=4)
    with pytest.raises(ConflictError, match="definition changed"):
        await chunk(factory, tenant_a, company, user, job, version=4)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(select(FieldIndexState))
            assert state is not None and state.ready_generation is None


async def test_index_tables_are_tenant_filtered_and_rebuild_fk_is_company_scoped(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company = uuid7()
    states = []
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            state = FieldIndexState(
                tenant_id=tenant, company_id=company, entity_type=ENTITY, field_key=KEY
            )
            session.add(state)
            await session.flush()
            states.append(state.id)
            session.add(
                FieldRebuildJob(
                    tenant_id=tenant,
                    company_id=company,
                    state_id=state.id,
                    actor_user_id=uuid7(),
                    generation=1,
                    source_version=1,
                    definition_digest="a" * 64,
                    definition={},
                )
            )
            await session.commit()
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            assert all(
                row.tenant_id == tenant for row in await session.scalars(select(FieldIndexState))
            )
            assert all(
                row.tenant_id == tenant for row in await session.scalars(select(FieldRebuildJob))
            )
    await session.rollback()
    with tenant_scope(tenant_a):
        session.add(
            FieldRebuildJob(
                tenant_id=tenant_a,
                company_id=uuid7(),
                state_id=states[0],
                actor_user_id=uuid7(),
                generation=2,
                source_version=1,
                definition_digest="a" * 64,
                definition={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_deep_custom_filter_is_validation_error(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth, _, _ = await setup(client, factory, tenant_a, company, user)
    response = await client.get(
        f"/v1/companies/{company}/item-groups",
        headers=auth,
        params={"custom_filters": "[" * 1100 + "0" + "]" * 1100},
    )
    assert response.status_code == 422, response.text


async def test_rebuild_transition_bounds_and_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.errors import ValidationFailedError

    from catalog.tasks.index_rebuilds import scoped_job
    from catalog.tasks.policy_state import company_policy_state

    company, user = uuid7(), uuid7()
    auth, _, _ = await setup(client, factory, tenant_a, company, user)
    job = await start(client, company, auth)
    base = path(company)
    for version in (0, 2):
        response = await client.post(
            base + "/rebuilds",
            json={"expected_version": version},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
        assert response.status_code == 409
    assert (
        await client.post(
            base + "/rebuilds/" + job["id"] + "/cancel",
            json={"expected_version": 2},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 409
    with pytest.raises(ValidationFailedError):
        await chunk(factory, tenant_a, company, user, job, limit=0)
    with pytest.raises(PermissionDeniedError, match="original actor"):
        await chunk(factory, tenant_a, company, uuid7(), job)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            with pytest.raises(PermissionDeniedError):
                await scoped_job(db, company, ENTITY, "cf_absent", uuid.UUID(job["id"]))
            with pytest.raises(PermissionDeniedError):
                await company_policy_state(db, uuid7(), company, lock=True)
            with pytest.raises(ValidationFailedError):
                await cleanup_chunk(
                    db,
                    tenant=uuid7(),
                    company=company,
                    entity=ENTITY,
                    key=KEY,
                    job_id=uuid.UUID(job["id"]),
                )
            with pytest.raises(ConflictError):
                await cleanup_chunk(
                    db,
                    tenant=tenant_a,
                    company=company,
                    entity=ENTITY,
                    key=KEY,
                    job_id=uuid.UUID(job["id"]),
                )
    completed = await chunk(factory, tenant_a, company, user, job)
    assert (
        await client.post(
            base + "/rebuilds/" + job["id"] + "/cancel",
            json={"expected_version": completed["row_version"]},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 409
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(select(FieldIndexState))
            assert state is not None
            state.generation = 2**63 - 1
            version = state.row_version
    assert (
        await client.post(
            base + "/rebuilds",
            json={"expected_version": version},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 409
    unsupported = base.replace(ENTITY, "catalog.unit_of_measure")
    assert (
        await client.post(
            unsupported + "/rebuilds",
            json={"expected_version": 0},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 422


async def test_expiry_before_commit_rolls_back_completed_chunk(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from catalog.tasks import index_rebuilds
    from catalog.tasks.identity_source import IdentitySourceUnavailableError

    company, user = uuid7(), uuid7()
    auth, _, _ = await setup(client, factory, tenant_a, company, user)
    job = await start(client, company, auth)
    from catalog.tasks.actor_authorization import require_job_actor

    original = require_job_actor
    calls = 0

    async def expires(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IdentitySourceUnavailableError("proof expired before commit")
        return await original(*args, **kwargs)

    monkeypatch.setattr(index_rebuilds, "require_job_actor", expires)
    with pytest.raises(IdentitySourceUnavailableError):
        await chunk(factory, tenant_a, company, user, job)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(CustomFieldValueIndex.id))) == 0
            state = await db.scalar(select(FieldIndexState))
            assert state is not None and state.ready_generation is None


async def test_rebuild_worker_defers_outages_and_cleans_failed_work(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform.service_auth import CompanyServiceScope

    from catalog.tasks import index_worker
    from catalog.tasks.identity_source import IdentitySourceUnavailableError
    from tests.test_identity_source_client import settings as source_settings

    company, user = uuid7(), uuid7()
    auth, _, _ = await setup(client, factory, tenant_a, company, user)
    job = await start(client, company, auth)
    settings = index_worker.IndexWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=source_settings(),
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),),
        index_chunk_size=1,
    )
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    mode = "offline"

    async def authorization(*args: Any, **kwargs: Any) -> Any:
        if mode == "offline":
            raise IdentitySourceUnavailableError("offline")
        return proof(
            tenant_a,
            company,
            user,
            source_version=3,
            permissions=permissions(ENTITY) if mode == "allowed" else frozenset(),
        )

    monkeypatch.setattr(index_worker, "fetch_actor_authorization", authorization)
    assert await index_worker.run_once(factory, settings, cursors) == 0
    assert await index_worker.run_once(factory, settings, cursors) == 0  # wrap fairness cursor
    mode = "allowed"
    assert await index_worker.run_once(factory, settings, cursors) == 1
    assert await index_worker.run_once(factory, settings, cursors) == 0
    mode = "denied"
    assert await index_worker.run_once(factory, settings, cursors) == 0
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(FieldRebuildJob, uuid.UUID(job["id"]))
            assert row is not None and row.status == "failed" and row.reason_code == "actor_denied"
    assert await index_worker.run_once(factory, settings, cursors) == 0

    async def busy_cleanup(*args: Any, **kwargs: Any) -> Any:
        raise ConflictError("another worker completed cleanup")

    with monkeypatch.context() as patch:
        patch.setattr(index_worker, "cleanup_chunk", busy_cleanup)
        assert await index_worker.run_once(factory, settings, cursors) == 0
    assert await index_worker.run_once(factory, settings, cursors) == 0
    assert await index_worker.run_once(factory, settings, cursors) == 1
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(CustomFieldValueIndex.id))) == 0
    with pytest.raises(ValueError):
        await index_worker.fail_build(
            factory,
            settings.source_subscriptions[0],
            ENTITY,
            KEY,
            uuid.UUID(job["id"]),
            1,
            "untrusted_reason",
        )
    await index_worker.fail_build(
        factory,
        settings.source_subscriptions[0],
        ENTITY,
        KEY,
        uuid.UUID(job["id"]),
        1,
        "actor_denied",
    )


async def test_protected_unprepared_and_unique_custom_index_guards(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.custom_query import CustomPredicate
    from billing_platform.errors import ValidationFailedError

    from catalog.models.classification import ItemGroup
    from catalog.tasks.field_context import load_field_context
    from catalog.tasks.field_indexes import apply_custom_filters, index_definition
    from tests.test_field_context import source_actor

    company, user = uuid7(), uuid7()
    auth, rows, facts = await setup(client, factory, tenant_a, company, user)
    url = f"/v1/companies/{company}/item-groups"
    for raw in (
        "{}",
        "[]",
        "not-json",
        json.dumps([{"key": KEY, "operator": "is_set", "value": True}] * 17),
    ):
        assert (
            await client.get(url, params={"custom_filters": raw}, headers=auth)
        ).status_code == 422
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            context = await load_field_context(
                db, source_actor(tenant_a, company, user), company, "catalog.unit_of_measure"
            )
            with pytest.raises(ValidationFailedError):
                index_definition(context, KEY)
            with pytest.raises(ValidationFailedError):
                await apply_custom_filters(
                    db,
                    select(ItemGroup.id),
                    context,
                    [CustomPredicate(key=KEY, operator="is_set", value=True)] * 17,
                )
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": ENTITY,
            "field_key": "custom_field:" + KEY,
            "subject_type": "user",
            "subject_id": str(user),
            "access": "read",
            "condition": {"field": "allowed_kind", "cmp": "eq", "value": "SERVICE"},
        },
    )
    await setup_source(factory, tenant_a, company, user, facts=(*facts, deny), version=4)
    assert (await client.get(path(company), headers=auth)).status_code == 403
    assert (await client.get(url, params=filter_query(), headers=auth)).status_code == 403
    unsearchable = tuple(
        row.model_copy(update={"data": {**row.data, "is_searchable": False}})
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    await setup_source(factory, tenant_a, company, user, facts=unsearchable, version=5)
    assert (await client.get(path(company), headers=auth)).status_code == 422
    unique = tuple(
        row.model_copy(update={"data": {**row.data, "validation": {"unique_within": "company"}}})
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    await setup_source(factory, tenant_a, company, user, facts=unique, version=6)
    assert (
        await client.post(
            path(company) + "/rebuilds",
            json={"expected_version": 0},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 409
    assert (
        await client.patch(
            url + "/" + rows[0]["id"],
            json={"expected_version": 1, "name": "Blocked"},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 409


async def test_worker_drift_and_invalid_required_data_fail_without_partial_activation(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform.service_auth import CompanyServiceScope

    from catalog.models.classification import ItemGroup
    from catalog.tasks import index_worker
    from tests.test_identity_source_client import settings as source_settings

    company, user = uuid7(), uuid7()
    auth, rows, facts = await setup(client, factory, tenant_a, company, user)
    job = await start(client, company, auth)
    settings = index_worker.IndexWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=source_settings(),
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),),
    )

    async def authorization(*args: Any, **kwargs: Any) -> Any:
        return proof(tenant_a, company, user, source_version=4, permissions=permissions(ENTITY))

    monkeypatch.setattr(index_worker, "fetch_actor_authorization", authorization)
    required = tuple(
        row.model_copy(update={"data": {**row.data, "is_required": True}})
        if row.kind == "field_config"
        else row
        for row in facts
    )
    await setup_source(factory, tenant_a, company, user, facts=required, version=4)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    assert await index_worker.run_once(factory, settings, cursors) == 0
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            failed = await db.get(FieldRebuildJob, uuid.UUID(job["id"]))
            assert failed is not None and failed.reason_code == "definition_changed"
    await index_worker.run_once(factory, settings, cursors)
    await index_worker.run_once(factory, settings, cursors)
    state = (await client.get(path(company), headers=auth)).json()
    second = await start(client, company, auth, state["row_version"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            owner = await db.get(ItemGroup, uuid.UUID(rows[0]["id"]))
            assert owner is not None
            owner.custom_fields = {KEY: None}
    assert await index_worker.run_once(factory, settings, cursors) == 0
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            failed = await db.get(FieldRebuildJob, uuid.UUID(second["id"]))
            assert failed is not None and failed.reason_code == "invalid_owner_value"
            assert await db.scalar(select(func.count(CustomFieldValueIndex.id))) == 0


async def test_multiselect_index_filters_do_not_duplicate_and_cleanup_members(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models.custom_fields import CustomFieldValueMember

    company, user = uuid7(), uuid7()
    facts = custom_facts(
        company,
        user,
        data_type="multi_select",
        options={"choices": [{"value": "red", "label": "Red"}, {"value": "blue", "label": "Blue"}]},
    )
    await setup_source(factory, tenant_a, company, user, facts=facts)
    auth = headers(company, permission=sorted(permissions(ENTITY)), tenant=tenant_a, user=user)
    for code, value in (("A", ["red", "blue"]), ("B", ["red"]), ("C", None)):
        response = await create(
            client,
            company,
            auth,
            "item-groups",
            {"code": code, "name": code, "valid_from": "2020-01-01", "custom_fields": {KEY: value}},
        )
        assert response.status_code == 201, response.text
    searchable = tuple(
        row.model_copy(update={"data": {**row.data, "is_searchable": True}})
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    await setup_source(factory, tenant_a, company, user, facts=searchable, version=3)
    job = await start(client, company, auth)
    await chunk(factory, tenant_a, company, user, job)
    url = f"/v1/companies/{company}/item-groups"
    for operator, query_value, expected in (
        ("has_any", ["red", "blue"], ["A", "B"]),
        ("has_all", ["red", "blue"], ["A"]),
        ("is_set", False, ["C"]),
    ):
        response = await client.get(
            url,
            headers=auth,
            params={
                "custom_filters": json.dumps(
                    [{"key": KEY, "operator": operator, "value": query_value}]
                )
            },
        )
        assert response.status_code == 200, response.text
        assert [row["code"] for row in response.json()["items"]] == expected
    state = (await client.get(path(company), headers=auth)).json()
    second = await start(client, company, auth, state["row_version"])
    await chunk(factory, tenant_a, company, user, second)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            cleaned = await cleanup_chunk(
                db,
                tenant=tenant_a,
                company=company,
                entity=ENTITY,
                key=KEY,
                job_id=uuid.UUID(second["id"]),
            )
            assert cleaned.cleanup_count == 3 and cleaned.phase == "complete"
            assert (
                await db.scalar(
                    select(func.count(CustomFieldValueMember.id)).where(
                        CustomFieldValueMember.generation == 1
                    )
                )
                == 0
            )


@pytest.mark.parametrize("other", ["building", "retired"])
async def test_ready_generation_cannot_be_retired_or_built_again(
    session: AsyncSession, tenant_a: uuid.UUID, other: str
) -> None:
    with tenant_scope(tenant_a):
        values: dict[str, Any] = {
            "tenant_id": tenant_a,
            "company_id": uuid7(),
            "entity_type": ENTITY,
            "field_key": KEY,
            "generation": 2,
            "ready_generation": 1,
            "ready_digest": "a" * 64,
            other + "_generation": 1,
        }
        if other == "building":
            values["building_digest"] = "a" * 64
        session.add(FieldIndexState(**values))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_cancellation_audit_columns_record_actual_operator(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, operator = uuid7(), uuid7(), uuid7()
    auth, _, facts = await setup(client, factory, tenant_a, company, user)
    job = await start(client, company, auth)
    await setup_source(
        factory,
        tenant_a,
        company,
        user,
        facts=(*facts, SnapshotRecord(kind="user", id=operator, data={"status": "active"})),
        version=4,
    )
    operator_headers = headers(
        company, permission=sorted(permissions(ENTITY)), tenant=tenant_a, user=operator
    )
    cancelled = await client.post(
        path(company) + "/rebuilds/" + job["id"] + "/cancel",
        headers={**operator_headers, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1},
    )
    assert cancelled.status_code == 200, cancelled.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(FieldRebuildJob, uuid.UUID(job["id"]))
            state = await db.scalar(select(FieldIndexState))
            assert row is not None and state is not None
            assert row.actor_user_id == user and row.updated_by == operator
            assert state.updated_by == operator

            await cleanup_chunk(
                db, tenant=tenant_a, company=company, entity=ENTITY, key=KEY, job_id=row.id
            )
            cleaned_job = await db.get(FieldRebuildJob, row.id, populate_existing=True)
            cleaned_state = await db.get(FieldIndexState, state.id, populate_existing=True)
            assert cleaned_job is not None and cleaned_state is not None
            assert (cleaned_job.actor_user_id, cleaned_job.created_by, cleaned_job.updated_by) == (
                user,
                user,
                None,
            )
            assert (cleaned_state.created_by, cleaned_state.updated_by) == (user, None)
