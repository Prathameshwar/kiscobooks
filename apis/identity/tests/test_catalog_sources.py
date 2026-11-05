from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from typing import Any, cast

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from billing_platform.snapshots import (
    SnapshotManifest,
    SnapshotPage,
    manifest_digest,
    verify_pages,
)
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import CatalogSourceCredential, CatalogSourceScope
from identity.events.catalog_source import CAPTURE_KEY, SOURCE_SPECS
from identity.models import Company
from identity.models.catalog_source import (
    CatalogSourceGeneration,
    CatalogSourcePage,
    CatalogSourceSnapshot,
)
from identity.tasks.catalog_snapshots import create_snapshot, read_page
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_field_policy, seed_two_companies

REQUEST_SECRET = b"ephemeral-source-request-test-key-000000000"
RESPONSE_SECRET = b"ephemeral-source-response-test-key-0000000"
REQUEST_KEY = ServiceKey(
    "catalog",
    "identity",
    frozenset({"catalog.snapshot.create", "catalog.snapshot.read"}),
    REQUEST_SECRET,
)
RESPONSE_KEY = ServiceKey(
    "identity", "catalog", frozenset({"catalog.snapshot.response"}), RESPONSE_SECRET
)


def prefix(tenant: uuid.UUID, company: uuid.UUID) -> str:
    return f"/internal/v1/tenants/{tenant}/companies/{company}/catalog-snapshots"


def headers(method: str, path: str, body: bytes = b"", **changes: str) -> dict[str, str]:
    operation = "catalog.snapshot.create" if method == "POST" else "catalog.snapshot.read"
    stamp = int(time.time())
    framed = service_request_bytes(method=method, path=path, query="", body=body)
    return {
        "content-type": "application/json",
        "x-source-key-id": "current",
        "x-source-issued-at": str(stamp),
        "x-source-signature": sign_service_body(
            REQUEST_KEY, key_id="current", operation=operation, timestamp=stamp, body=framed
        ),
        **changes,
    }


def configure(app: object, scopes: list[tuple[uuid.UUID, uuid.UUID]]) -> FastAPI:
    application = cast(FastAPI, app)
    settings = application.state.settings
    settings.catalog_source_credentials = {
        "current": CatalogSourceCredential(
            secret=SecretStr(REQUEST_SECRET.decode()),
            scopes=tuple(CatalogSourceScope(tenant_id=t, company_id=c) for t, c in scopes),
        )
    }
    settings.catalog_source_response_secret = SecretStr(RESPONSE_SECRET.decode())
    return application


def verify_response(response: httpx.Response, method: str, path: str, body: bytes = b"") -> None:
    verify_service_body(
        {"current": RESPONSE_KEY},
        key_id=response.headers["x-source-key-id"],
        issuer="identity",
        audience="catalog",
        operation="catalog.snapshot.response",
        timestamp=response.headers["x-source-issued-at"],
        signature=response.headers["x-source-signature"],
        now=int(time.time()),
        body=service_response_bytes(
            request_bytes=service_request_bytes(method=method, path=path, query="", body=body),
            response_body=response.content,
        ),
    )


async def test_real_source_api_complete_empty_sets_scope_and_signed_replay(
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    configure(app, [(tenant_a, company), (tenant_b, foreign)])
    path = prefix(tenant_a, company)
    body = json.dumps({"request_id": str(uuid7())}).encode()
    assert (await client.post(path, content=body)).status_code == 401
    response = await client.post(path, content=body, headers=headers("POST", path, body))
    assert response.status_code == 200, response.text
    verify_response(response, "POST", path, body)
    manifest = SnapshotManifest.model_validate(response.json())
    assert manifest.stream_counts["field_policy"] == 0
    assert manifest.stream_counts["custom_definition"] == 0
    assert set(manifest.stream_counts) == set(SOURCE_SPECS)
    assert manifest.stream_counts["company"] == 1
    replay = await client.post(path, content=body, headers=headers("POST", path, body))
    assert replay.json() == response.json()
    pages = []
    for number in range(len(manifest.page_sha256)):
        page_path = f"{path}/{manifest.snapshot_id}/pages/{number}"
        page = await client.get(page_path, headers=headers("GET", page_path))
        assert page.status_code == 200
        verify_response(page, "GET", page_path)
        pages.append(SnapshotPage.model_validate(page.json()))
    records = verify_pages(manifest, pages)
    company_row = next(record for record in records if record.kind == "company")
    assert company_row.id == company and company_row.data["display_name"] == "Alpha Ltd"
    assert "cash_receipt_limit" not in company_row.data
    assert "legal_name" not in company_row.data
    manifest_path = f"{path}/{manifest.snapshot_id}"
    assert (
        await client.get(manifest_path, headers=headers("GET", manifest_path))
    ).json() == response.json()
    foreign_path = f"{prefix(tenant_b, foreign)}/{manifest.snapshot_id}"
    assert (await client.get(foreign_path, headers=headers("GET", foreign_path))).status_code == 404
    ungranted = prefix(tenant_a, uuid7())
    assert (
        await client.post(ungranted, content=body, headers=headers("POST", ungranted, body))
    ).status_code == 403
    assert (
        await client.post(
            path,
            content=body,
            headers=headers("POST", path, body, **{"x-source-signature": "0" * 64}),
        )
    ).status_code == 401
    assert (
        await client.post(path, content=b"x" * 4097, headers=headers("POST", path, b"x" * 4097))
    ).status_code == 422
    assert (
        await client.post(path, content=b"{}", headers=headers("POST", path, b"{}"))
    ).status_code == 422
    other_path = prefix(tenant_b, foreign)
    other = await client.post(other_path, content=body, headers=headers("POST", other_path, body))
    assert other.status_code == 200, other.text
    for scoped, target in [(tenant_a, company), (tenant_b, foreign)]:
        with tenant_scope(scoped):
            tables: tuple[
                type[CatalogSourceSnapshot]
                | type[CatalogSourcePage]
                | type[CatalogSourceGeneration],
                ...,
            ] = (CatalogSourceSnapshot, CatalogSourcePage, CatalogSourceGeneration)
            for model in tables:
                rows = list(await session.scalars(select(model)))
                assert rows, model.__tablename__
                for row in rows:
                    assert isinstance(
                        row, CatalogSourceSnapshot | CatalogSourcePage | CatalogSourceGeneration
                    )
                    assert row.tenant_id == scoped
            assert all(
                row.company_id == target
                for row in await session.scalars(select(CatalogSourceSnapshot))
            )


async def test_native_write_publishes_complete_versioned_source_in_same_transaction(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    response = await client.patch(
        f"/v1/companies/{company}",
        json={"display_name": "Revised"},
        headers=actor_headers(
            tenant_id=tenant_a,
            user_id=uuid7(),
            grants=[grant(["company.update"])],
        ),
    )
    assert response.status_code == 200, response.text
    messages = list(
        await session.scalars(
            select(Outbox).where(Outbox.event_type == "identity.catalog_context.changed")
        )
    )
    assert len(messages) == 1
    event = messages[0].payload
    assert event["records"][0]["data"]["display_name"] == "Revised"
    assert event["records"][0]["data"]["base_currency"] == "INR"
    assert event["source_version"] > 0
    assert "changes" not in event
    with tenant_scope(tenant_a):
        generation = (await session.scalars(select(CatalogSourceGeneration))).one().version
        session.sync_session.info[CAPTURE_KEY] = True
        row = await session.get(Company, company)
        assert row is not None
        row.display_name = "Rolled back"
        await session.flush()
        await session.rollback()
        assert (await session.scalars(select(CatalogSourceGeneration))).one().version == generation
        assert (
            len(
                list(
                    await session.scalars(
                        select(Outbox).where(
                            Outbox.event_type == "identity.catalog_context.changed"
                        )
                    )
                )
            )
            == 1
        )


async def test_policy_tombstone_snapshot_integrity_expiry_and_company_access(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    other = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_company(tenant_id=tenant_a, company_id=other, code="SECOND"))
        await session.commit()
        policy = build_field_policy(
            tenant_id=tenant_a,
            subject_type="user",
            subject_id=uuid7(),
            entity_type="catalog.item",
            field_key="name",
        )
        session.sync_session.info[CAPTURE_KEY] = True
        session.add(policy)
        await session.commit()
        first = await create_snapshot(
            session, company_id=company, request_id=uuid7(), ttl_seconds=60
        )
        await session.commit()
        await session.delete(policy)
        await session.commit()
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "identity.catalog_context.changed")
            )
        )
        assert events[-1].payload["records"] == [
            {"kind": "field_policy", "id": str(policy.id), "deleted": True, "data": {}}
        ]
        second = await create_snapshot(
            session, company_id=company, request_id=uuid7(), ttl_seconds=60
        )
        await session.commit()
        assert (
            first.stream_counts["field_policy"] == 1 and second.stream_counts["field_policy"] == 0
        )
        assert second.source_version > first.source_version
        from billing_platform.errors import PermissionDeniedError

        with pytest.raises(PermissionDeniedError):
            await read_page(session, company_id=other, snapshot_id=first.snapshot_id, page_number=0)
        page = (
            await session.scalars(
                select(CatalogSourcePage).where(CatalogSourcePage.snapshot_id == first.snapshot_id)
            )
        ).one()
        page.content_sha256 = "0" * 64
        await session.flush()
        with pytest.raises(ConflictError):
            await read_page(
                session, company_id=company, snapshot_id=first.snapshot_id, page_number=0
            )
        snapshot = await session.get(CatalogSourceSnapshot, second.snapshot_id)
        assert snapshot is not None
        snapshot.expires_at = utcnow() - dt.timedelta(seconds=1)
        await session.flush()
        with pytest.raises(ConflictError):
            await create_snapshot(
                session, company_id=company, request_id=snapshot.request_id, ttl_seconds=60
            )
        with pytest.raises(ValidationFailedError):
            await create_snapshot(
                session, company_id=company, request_id=uuid.UUID(int=0), ttl_seconds=60
            )


async def test_source_capture_rejects_owner_laundering(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        assert row is not None
    row.tenant_id = tenant_b
    row.code = "LAUNDERED"
    session.sync_session.info[CAPTURE_KEY] = True
    with tenant_scope(tenant_b), pytest.raises(ValidationFailedError, match="ownership"):
        await session.flush()
    await session.rollback()


async def test_source_versions_cover_snapshots_replays_and_multiple_flushes(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from sqlalchemy import text, update

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        session.sync_session.info[CAPTURE_KEY] = True
        request_id = uuid7()
        first = await create_snapshot(
            session, company_id=company, request_id=request_id, ttl_seconds=60
        )
        await session.commit()
        replay = await create_snapshot(
            session, company_id=company, request_id=request_id, ttl_seconds=60
        )
        assert replay == first
        row = await session.get(Company, company)
        assert row is not None
        row.display_name = "First flush"
        await session.flush()
        row.display_name = "Second flush"
        await session.commit()
        events = list(
            await session.scalars(
                select(Outbox)
                .where(Outbox.event_type == "identity.catalog_context.changed")
                .order_by(Outbox.id)
            )
        )
        versions = [event.payload["source_version"] for event in events]
        assert versions == list(range(first.source_version, first.source_version + 4))
        assert all(
            event.payload["previous_version"] == event.payload["source_version"] - 1
            for event in events
        )
        assert [event.payload["records"] for event in events[:2]] == [[], []]
        assert events[-2].payload["records"][0]["data"]["display_name"] == "First flush"
        assert events[-1].payload["records"][0]["data"]["display_name"] == "Second flush"
        with pytest.raises(ValidationFailedError, match="tracked ORM"):
            await session.execute(update(Company).values(display_name="uncaptured"))
        with pytest.raises(ValidationFailedError, match="source capture"):
            await session.execute(text("SELECT 1"))


async def test_expired_source_cache_cleanup_keeps_current_lease_and_company_scope(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from identity.tasks.catalog_snapshots import prune_expired_snapshots

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        first = await create_snapshot(
            session, company_id=company, request_id=uuid7(), ttl_seconds=60
        )
        await session.commit()
        old = await session.get(CatalogSourceSnapshot, first.snapshot_id)
        assert old is not None
        old.expires_at = utcnow() - dt.timedelta(minutes=6)
        await session.commit()
        assert await prune_expired_snapshots(session, company_id=uuid7()) == 0
        assert await prune_expired_snapshots(session, company_id=company) == 1
        await session.commit()
        assert not list(await session.scalars(select(CatalogSourcePage)))
        second = await create_snapshot(
            session, company_id=company, request_id=uuid7(), ttl_seconds=60
        )
        assert await prune_expired_snapshots(session, company_id=company) == 0
        assert await session.get(CatalogSourceSnapshot, second.snapshot_id) is not None


@pytest.mark.parametrize("artifact", ["manifest", "page", "scope", "page_identity"])
async def test_corrupt_source_artifact_is_not_signed(
    artifact: str,
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    configure(app, [(tenant_a, company)])
    path = prefix(tenant_a, company)
    body = json.dumps({"request_id": str(uuid7())}).encode()
    response = await client.post(path, content=body, headers=headers("POST", path, body))
    manifest = SnapshotManifest.model_validate(response.json())
    with tenant_scope(tenant_a):
        row = await session.get(CatalogSourceSnapshot, manifest.snapshot_id)
        assert row is not None
        if artifact in {"manifest", "scope"}:
            row.manifest = (
                {} if artifact == "manifest" else {**row.manifest, "company_id": str(uuid7())}
            )
            target = f"{path}/{manifest.snapshot_id}"
        else:
            page = (await session.scalars(select(CatalogSourcePage))).one()
            page.payload = (
                {} if artifact == "page" else {**page.payload, "snapshot_id": str(uuid7())}
            )
            # Even a self-consistent digest must match the artifact's identity.
            if artifact == "page_identity":
                digest = SnapshotPage.model_validate(page.payload).digest()
                page.content_sha256 = digest
                row.manifest = {
                    **row.manifest,
                    "page_sha256": [digest],
                    "content_sha256": manifest_digest((digest,)),
                }
            target = f"{path}/{manifest.snapshot_id}/pages/0"
        await session.commit()
    result = await client.get(target, headers=headers("GET", target))
    assert result.status_code == 409, result.text
    assert "x-source-signature" not in result.headers
    assert "integrity" in result.json()["error"]["message"]


def test_source_openapi_declares_authentication_headers(app: object) -> None:
    schema = cast(FastAPI, app).openapi()
    paths = {
        path: methods
        for path, methods in schema["paths"].items()
        if path.startswith("/internal/v1/tenants/")
        and any(
            namespace in path for namespace in ("/catalog-snapshots", "/catalog-authorizations")
        )
    }
    assert len(paths) == 4
    for methods in paths.values():
        operation = next(value for key, value in methods.items() if key in {"get", "post"})
        names = {
            parameter["name"]
            for parameter in operation["parameters"]
            if parameter["in"] == "header" and parameter.get("required")
        }
        assert names == {"x-source-key-id", "x-source-issued-at", "x-source-signature"}


async def test_owner_subject_and_role_updates_remain_minimal_and_revoke_in_source(
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    from tests.factories import build_user

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    configure(app, [(tenant_a, company)])
    subject, manager, administrator = uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add_all(
            [
                build_user(tenant_id=tenant_a, user_id=subject, email="subject@example.test"),
                build_user(tenant_id=tenant_a, user_id=manager, email="manager@example.test"),
            ]
        )
        await session.commit()
    auth = actor_headers(
        tenant_id=tenant_a,
        user_id=administrator,
        grants=[
            grant(
                [
                    "user.read",
                    "user.update",
                    "user.deactivate",
                    "role.manage",
                    "role.read",
                    "role.assign",
                    "unit.read",
                    "unit.manage",
                ]
            )
        ],
    )
    path = f"/v1/users/{subject}"
    updated = await client.patch(
        path,
        json={
            "display_name": "Private display name",
            "job_title": "Specialist",
            "reporting_manager_id": str(manager),
        },
        headers=auth,
    )
    assert updated.status_code == 200, updated.text
    assert (
        await client.patch(path, json={"display_name": "Private display name"}, headers=auth)
    ).status_code == 200
    assert (
        await client.patch(path, json={"reporting_manager_id": str(uuid7())}, headers=auth)
    ).status_code == 422
    assert (await client.patch(path, json={"job_title": None}, headers=auth)).status_code == 200
    created = await client.post(
        "/v1/roles",
        json={"key": "catalog_editor", "name": "Catalog editor", "permissions": ["unit.read"]},
        headers=auth,
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["role"]["id"]
    for body in [
        {
            "name": "Catalog maintainer",
            "description": "Scoped catalog definitions",
            "scope_hint": "company",
            "permissions": ["unit.read", "unit.manage"],
        },
        {},
    ]:
        revised = await client.patch(f"/v1/roles/{role_id}", json=body, headers=auth)
        assert revised.status_code == 200, revised.text
    assigned = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": role_id,
            "scope_type": "company",
            "scope_id": str(company),
            "valid_from": "2020-01-01",
        },
        headers=auth,
    )
    assert assigned.status_code == 201, assigned.text
    assignment_id = assigned.json()["id"]
    revoked = await client.post(
        f"/v1/role-assignments/{assignment_id}/revoke",
        json={"reason": "Catalog access removed"},
        headers=auth,
    )
    assert revoked.status_code == 200 and revoked.json()["is_active"] is False
    listed = await client.get(
        "/v1/role-assignments",
        params={
            "subject_id": str(subject),
            "subject_type": "user",
            "role_id": role_id,
            "scope_type": "company",
            "active": "false",
        },
        headers=auth,
    )
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    list_queries: list[dict[str, Any]] = [
        {"q": "Private", "status": "active", "user_type": "tenant_user", "sort": "display_name"},
        {"limit": 1, "sort": "display_name"},
    ]
    for params in list_queries:
        users = await client.get("/v1/users", params=params, headers=auth)
        assert users.status_code == 200, users.text
    source_path = prefix(tenant_a, company)
    request = json.dumps({"request_id": str(uuid7())}).encode()
    source = await client.post(
        source_path, content=request, headers=headers("POST", source_path, request)
    )
    manifest = SnapshotManifest.model_validate(source.json())
    with tenant_scope(tenant_a):
        page = await read_page(
            session, company_id=company, snapshot_id=manifest.snapshot_id, page_number=0
        )
        projected = next(record for record in page.records if str(record.id) == assignment_id)
        assert projected.data["is_active"] is False
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "identity.catalog_context.changed")
            )
        )
        records = [record for event in events for record in event.payload["records"]]
        assert any(
            record["kind"] == "role_assignment" and record["data"]["is_active"] is False
            for record in records
        )
        assert all(
            set(record["data"]) == {"status"} for record in records if record["kind"] == "user"
        )
        assert all("Private display name" not in json.dumps(event.payload) for event in events)
    deactivated = await client.post(
        path + "/deactivate", json={"reason": "Access removed"}, headers=auth
    )
    assert deactivated.status_code == 200
    assert (
        await client.patch(path, json={"display_name": "Cannot restore"}, headers=auth)
    ).status_code == 409
