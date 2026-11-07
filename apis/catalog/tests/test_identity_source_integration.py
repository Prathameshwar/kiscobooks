"""Actual HTTP producer/consumer verification with isolated service processes."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.projections import CompanyProjection
from catalog.tasks.identity_source import (
    IdentitySourceSettings,
    IdentitySourceUnavailableError,
    fetch_identity_snapshot,
)
from catalog.tasks.projections import activate_snapshot, require_identity_context

ROOT = Path(__file__).resolve().parents[3]


async def test_real_identity_bulk_worker_continues_without_idle_gap_and_stops_revocation(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
) -> None:
    import base64
    import hashlib
    import hmac
    import time

    from billing_platform.service_auth import CompanyServiceScope

    from catalog.models import UnitOfMeasure
    from catalog.tasks.bulk_worker import BulkWorkerSettings, run_once
    from tests.bulk_factories import post, unit_row
    from tests.conftest import ACTOR_SECRET
    from tests.test_api import headers

    settings, info = identity_server
    tenant, company, user = (uuid.UUID(info[key]) for key in ("tenant_id", "company_id", "user_id"))
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
    permissions = [
        "catalog.bulk.read",
        "catalog.bulk.manage",
        "catalog.bulk.commit",
        "unit.read",
        "unit.manage",
    ]
    auth = headers(company, tenant=tenant, user=user, permission=permissions)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(
        client,
        root,
        auth,
        "",
        {"format": "JSON", "records": [unit_row("first"), unit_row("second")]},
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    config = BulkWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=settings,
        actor_signing_secret=SecretStr(ACTOR_SECRET),
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    assert await run_once(factory, config, cursors) == 1
    # Refreshing an unchanged snapshot renews the lease without invalidating
    # product drafts or advancing the source event stream.
    renewed = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    assert renewed.manifest.source_version == source.manifest.source_version
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, renewed)
    assert await run_once(factory, config, cursors) == 1
    ready = (await client.get(root + "/" + job["id"], headers=auth)).json()
    assert ready["state"] == "READY"
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {
            "expected_version": ready["row_version"],
            "selection_digest": ready["selection_digest"],
        },
    )
    assert await run_once(factory, config, cursors) == 1
    raw = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant),
            "user_id": str(user),
            "grants": [
                {
                    "permissions": ["role.manage", *permissions],
                    "scope_type": "tenant",
                    "scope_id": None,
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                    "is_active": True,
                }
            ],
        }
    ).encode()
    signed = {
        "x-actor-context": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "x-actor-signature": hmac.new(
            info["actor_secret"].encode(), raw, hashlib.sha256
        ).hexdigest(),
    }
    async with httpx.AsyncClient(base_url=settings.base_url, trust_env=False) as owner:
        response = await owner.patch(
            f"/v1/roles/{info['role_id']}",
            headers=signed,
            json={"permissions": [p for p in permissions if p != "catalog.bulk.commit"]},
        )
        assert response.status_code == 200, response.text
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
    assert await run_once(factory, config, cursors) == 0
    stopped = (await client.get(root + "/" + job["id"], headers=auth)).json()
    assert stopped["state"] == "PARTIAL" and stopped["completed_count"] == 1
    with tenant_scope(tenant):
        async with factory() as db:
            assert list(await db.scalars(select(UnitOfMeasure.code))) == ["FIRST"]


@pytest_asyncio.fixture
async def identity_server() -> AsyncIterator[tuple[IdentitySourceSettings, dict[str, Any]]]:
    owner = ROOT / "apis/identity"
    python = owner / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        pytest.fail("real Identity contract test requires its installed service environment")
    credentials = {
        name: secrets.token_hex(32)
        for name in ("request_secret", "response_secret", "actor_secret")
    }
    # Identity has its own coverage gate. pytest-cov's inherited process hook
    # would resolve relative source paths against the owner's cwd and merge two
    # services into Catalog's denominator. Keep this wire test boundary explicit.
    child_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
    }
    process = await asyncio.create_subprocess_exec(
        str(python),
        "-m",
        "tools.catalog_source_test_server",
        cwd=owner,
        env=child_environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(credentials).encode() + b"\n")
        await process.stdin.drain()
        line = await asyncio.wait_for(process.stdout.readline(), timeout=30)
        if not line:
            assert process.stderr is not None
            pytest.fail((await process.stderr.read()).decode())
        info = json.loads(line)
        settings = IdentitySourceSettings(
            base_url=f"http://127.0.0.1:{info['port']}",
            request_secret=SecretStr(credentials["request_secret"]),
            response_secrets={"current": SecretStr(credentials["response_secret"])},
        )
        async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
            for _ in range(100):
                try:
                    if (await client.get(settings.base_url + "/health/live")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
            else:
                pytest.fail("ephemeral Identity source server did not start")
        yield settings, {**info, **credentials}
    finally:
        if process.returncode is None:
            process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)


async def test_catalog_fetches_real_identity_snapshot_and_rejects_ungranted_scope(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
) -> None:
    settings, info = identity_server
    tenant, company = uuid.UUID(info["tenant_id"]), uuid.UUID(info["company_id"])
    request_id = uuid7()
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=request_id
    )
    assert source.manifest.stream_counts["company"] == 1
    assert source.manifest.stream_counts["field_policy"] == 0
    assert source.records[0].data["base_currency"] == "INR"
    replay = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=request_id
    )
    assert replay == source
    foreign = await fetch_identity_snapshot(
        settings,
        tenant_id=uuid.UUID(info["other_tenant_id"]),
        company_id=uuid.UUID(info["other_company_id"]),
        request_id=uuid7(),
    )
    assert all(record.id != company for record in foreign.records)
    with pytest.raises(IdentitySourceUnavailableError):
        await fetch_identity_snapshot(
            settings, tenant_id=tenant, company_id=uuid7(), request_id=uuid7()
        )
    bad = settings.model_copy(
        update={"response_secrets": {"current": SecretStr(secrets.token_hex(32))}}
    )
    with pytest.raises(IdentitySourceUnavailableError):
        await fetch_identity_snapshot(bad, tenant_id=tenant, company_id=company, request_id=uuid7())


async def test_real_owner_snapshot_activates_catalog_in_one_transaction(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
) -> None:
    settings, info = identity_server
    tenant, company = uuid.UUID(info["tenant_id"]), uuid.UUID(info["company_id"])
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            checkpoint = await activate_snapshot(db, source)
            assert checkpoint.status == "ready"
        async with factory.begin() as db:
            checkpoint = await require_identity_context(db, company)
            row = (await db.scalars(select(CompanyProjection))).one()
            assert row.source_id == company and row.base_currency == "INR"
            assert row.source_version == checkpoint.source_version
        changed = await fetch_identity_snapshot(
            settings, tenant_id=tenant, company_id=company, request_id=uuid7()
        )
        async with factory() as db:
            await db.begin()
            await activate_snapshot(db, changed)
            await db.rollback()
        async with factory.begin() as db:
            assert (
                await require_identity_context(db, company)
            ).source_version == source.manifest.source_version


async def test_real_owner_context_drives_catalog_metadata(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
) -> None:
    from tests.test_api import headers

    settings, info = identity_server
    tenant, company, user = (
        uuid.UUID(info["tenant_id"]),
        uuid.UUID(info["company_id"]),
        uuid.UUID(info["user_id"]),
    )
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.unit_of_measure/field-set",
        headers=headers(company, permission="unit.read", tenant=tenant, user=user),
    )
    assert response.status_code == 200, response.text
    assert response.json()["source_version"] == source.manifest.source_version
    assert len(response.json()["fields"]) == 8

    from tests.test_unit_api import UNIT_BODY, access

    route = f"/v1/companies/{company}/units"
    write = access(tenant, company, user, "unit.manage", key="actual-owner-unit")
    created = await client.post(route, json=UNIT_BODY, headers=write)
    assert created.status_code == 201, created.text
    assert (await client.post(route, json=UNIT_BODY, headers=write)).json() == created.json()
    listed = await client.get(route, headers=access(tenant, company, user, "unit.read"))
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == created.json()["id"]
    readiness = await client.get(
        f"/v1/companies/{company}/catalog-readiness",
        headers=access(tenant, company, user, "item.read"),
    )
    assert readiness.json()["company_verified"] is True
    assert all(
        source["status"] == "ready"
        for source in readiness.json()["sources"]
        if source["owner"] == "identity"
    )


async def test_worker_refreshes_real_sources_and_never_extends_lease_on_failure(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
) -> None:
    from catalog.tasks.source_worker import Subscription, WorkerSettings, refresh_once

    settings, info = identity_server
    tenant, company = uuid.UUID(info["tenant_id"]), uuid.UUID(info["company_id"])
    config = WorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=settings,
        source_subscriptions=(Subscription(tenant_id=tenant, company_id=company),),
        source_broker_url=SecretStr("amqp://ephemeral.invalid"),
        source_broker_user="identity",
        source_event_secret=SecretStr(secrets.token_hex(32)),
    )
    await refresh_once(factory, config)
    with tenant_scope(tenant):
        async with factory.begin() as db:
            lease = (await require_identity_context(db, company)).expires_at
    bad_source = settings.model_copy(
        update={"response_secrets": {"current": SecretStr(secrets.token_hex(32))}}
    )
    await refresh_once(factory, config.model_copy(update={"identity_source": bad_source}))
    with tenant_scope(tenant):
        async with factory.begin() as db:
            assert (await require_identity_context(db, company)).expires_at == lease


async def test_real_owner_authorization_tracks_permission_revocation(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
) -> None:
    import base64
    import hashlib
    import hmac
    import time

    from billing_platform.authz import ScopePath
    from billing_platform.errors import PermissionDeniedError

    from catalog.tasks.actor_authorization import fetch_actor_authorization, require_job_actor

    settings, info = identity_server
    tenant, company, user = (uuid.UUID(info[key]) for key in ("tenant_id", "company_id", "user_id"))
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    proof = await fetch_actor_authorization(
        settings,
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        permissions=frozenset({"unit.manage"}),
    )
    assert proof.source_version == source.manifest.source_version and proof.permissions == {
        "unit.manage"
    }
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
            actor = await require_job_actor(
                db, proof, company_id=company, user_id=user, permissions=frozenset({"unit.manage"})
            )
            assert actor.allows_scope("unit.manage", target=ScopePath(company_id=company))
    # Revoke through the actual Identity role API, using its normal gateway contract.
    raw = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant),
            "user_id": str(user),
            "grants": [
                {
                    "permissions": ["role.manage", "unit.manage", "unit.read"],
                    "scope_type": "tenant",
                    "scope_id": None,
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                    "is_active": True,
                }
            ],
        }
    ).encode()
    headers = {
        "x-actor-context": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "x-actor-signature": hmac.new(
            info["actor_secret"].encode(), raw, hashlib.sha256
        ).hexdigest(),
    }
    async with httpx.AsyncClient(base_url=settings.base_url, trust_env=False) as client:
        response = await client.patch(
            f"/v1/roles/{info['role_id']}", json={"permissions": ["unit.read"]}, headers=headers
        )
        assert response.status_code == 200, response.text
    revoked = await fetch_actor_authorization(
        settings,
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        permissions=frozenset({"unit.manage"}),
    )
    assert revoked.source_version > proof.source_version and not revoked.permissions
    current = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    revoked = await fetch_actor_authorization(
        settings,
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        permissions=frozenset({"unit.manage"}),
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, current)
            with pytest.raises(PermissionDeniedError):
                await require_job_actor(
                    db,
                    revoked,
                    company_id=company,
                    user_id=user,
                    permissions=frozenset({"unit.manage"}),
                )
    with pytest.raises(IdentitySourceUnavailableError):
        await fetch_actor_authorization(
            settings,
            tenant_id=tenant,
            company_id=uuid7(),
            user_id=user,
            permissions=frozenset({"unit.manage"}),
        )


async def test_real_owner_authorizes_rebuild_worker_and_revocation_stops_next_generation(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
) -> None:
    import base64
    import hashlib
    import hmac
    import time

    from billing_platform.service_auth import CompanyServiceScope

    from catalog.tasks.index_rebuilds import permissions
    from catalog.tasks.index_worker import IndexWorkerSettings, run_once
    from tests.test_api import headers as catalog_headers
    from tests.test_classification_api import create
    from tests.test_index_rebuilds import ENTITY, filter_query, path, start

    settings, info = identity_server
    tenant, company, user = (uuid.UUID(info[key]) for key in ("tenant_id", "company_id", "user_id"))
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
    auth = catalog_headers(
        company, permission=sorted(permissions(ENTITY)), tenant=tenant, user=user
    )
    first = await start(client, company, auth)
    config = IndexWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=settings,
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    assert await run_once(factory, config, cursors) == 1
    finished = await client.get(path(company) + "/rebuilds/" + first["id"], headers=auth)
    assert finished.json()["status"] == "succeeded"
    created = await create(
        client,
        company,
        auth,
        "item-groups",
        {
            "code": "ACTUAL",
            "name": "Actual owner source",
            "valid_from": "2020-01-01",
            "custom_fields": {"cf_note": "native"},
        },
    )
    assert created.status_code == 201, created.text
    result = await client.get(
        f"/v1/companies/{company}/item-groups", params=filter_query("native"), headers=auth
    )
    assert result.status_code == 200 and result.json()["items"][0]["id"] == created.json()["id"]
    state = (await client.get(path(company), headers=auth)).json()
    second = await start(client, company, auth, state["row_version"])
    body = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant),
            "user_id": str(user),
            "grants": [
                {
                    "permissions": ["role.manage", "item_group.read"],
                    "scope_type": "tenant",
                    "scope_id": None,
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                    "is_active": True,
                }
            ],
        }
    ).encode()
    signed = {
        "x-actor-context": base64.urlsafe_b64encode(body).decode().rstrip("="),
        "x-actor-signature": hmac.new(
            info["actor_secret"].encode(), body, hashlib.sha256
        ).hexdigest(),
    }
    async with httpx.AsyncClient(base_url=settings.base_url, trust_env=False) as owner:
        removed = await owner.patch(
            f"/v1/roles/{info['role_id']}",
            json={"permissions": ["item_group.read"]},
            headers=signed,
        )
        assert removed.status_code == 200, removed.text
    current = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, current)
    assert await run_once(factory, config, cursors) == 0
    failed = await client.get(path(company) + "/rebuilds/" + second["id"], headers=auth)
    assert failed.json()["status"] == "failed" and failed.json()["reason_code"] == "actor_denied"
    assert await run_once(factory, config, cursors) == 0
    assert await run_once(factory, config, cursors) == 1
    assert (await client.get(path(company), headers=auth)).json()["ready_generation"] == 1
