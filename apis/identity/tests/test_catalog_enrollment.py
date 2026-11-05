"""Automatic Catalog enrollment is an explicit service capability, never a wildcard."""

import json
import time
import uuid
from typing import cast

import httpx
import pytest
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import CatalogSourceCredential
from identity.models import CatalogSourceEnrollment, Company, PlatformInstallation
from identity.seeds.roles import seed_system_roles
from identity.tasks.catalog_enrollment import backfill
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_catalog_source_enrollment,
    build_user,
    seed_two_companies,
    seed_two_tenants,
)
from tests.test_api_companies import _valid_company_body
from tests.test_catalog_sources import REQUEST_SECRET, RESPONSE_SECRET, configure, headers, prefix

DISCOVERY = "/internal/v1/catalog-enrollments"


def discovery_headers(body: bytes) -> dict[str, str]:
    operation = "catalog.enrollment.read"
    stamp = int(time.time())
    return {
        "x-source-key-id": "current",
        "x-source-issued-at": str(stamp),
        "x-source-signature": sign_service_body(
            ServiceKey("catalog", "identity", frozenset({operation}), REQUEST_SECRET),
            key_id="current",
            operation=operation,
            timestamp=stamp,
            body=service_request_bytes(method="POST", path=DISCOVERY, query="", body=body),
        ),
        "content-type": "application/json",
    }


async def test_company_creation_enrolls_atomically_and_denied_creation_does_not(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=user_id))
        await session.commit()
    denied = await client.post(
        "/v1/companies",
        json=_valid_company_body(),
        headers=actor_headers(tenant_id=tenant_a, user_id=user_id),
    )
    assert denied.status_code == 403
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(CatalogSourceEnrollment.id))) == 0
    created = await client.post(
        "/v1/companies",
        json=_valid_company_body(),
        headers=actor_headers(
            tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.create"])]
        ),
    )
    assert created.status_code == 201, created.text
    with tenant_scope(tenant_a):
        row = (await session.scalars(select(CatalogSourceEnrollment))).one()
        assert str(row.company_id) == created.json()["id"] and row.is_active
        assert row.created_by == user_id
    with tenant_scope(tenant_b):
        assert await session.scalar(select(func.count(CatalogSourceEnrollment.id))) == 0


async def test_signed_discovery_paging_scope_and_revocation(
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    a, b = await seed_two_companies(session, tenant_a, tenant_b)
    configure(app, [(tenant_a, a)])
    body = b'{"limit":1}'
    assert (await client.post(DISCOVERY, content=body)).status_code == 401
    assert (
        await client.post(DISCOVERY, content=body, headers=discovery_headers(body))
    ).status_code == 401
    settings = cast(FastAPI, app).state.settings
    settings.catalog_source_credentials = {
        "current": CatalogSourceCredential(
            secret=SecretStr(REQUEST_SECRET.decode()), scopes=(), allow_enrolled_companies=True
        )
    }
    with unfiltered():
        session.add(
            PlatformInstallation(
                id=uuid7(), key="platform", completed_at=utcnow(), tenant_id=tenant_a
            )
        )
        session.add_all(
            [
                build_catalog_source_enrollment(tenant_id=t, company_id=c)
                for t, c in ((tenant_a, a), (tenant_b, b))
            ]
        )
        await session.commit()
    response = await client.post(DISCOVERY, content=body, headers=discovery_headers(body))
    assert response.status_code == 200, response.text
    evidence = await session.scalar(
        select(Outbox).where(Outbox.event_type == "catalog_source.discovery_read")
    )
    assert evidence is not None and evidence.tenant_id == tenant_a
    verify_service_body(
        {
            "current": ServiceKey(
                "identity", "catalog", frozenset({"catalog.enrollment.response"}), RESPONSE_SECRET
            )
        },
        key_id="current",
        issuer="identity",
        audience="catalog",
        operation="catalog.enrollment.response",
        timestamp=response.headers["x-source-issued-at"],
        signature=response.headers["x-source-signature"],
        now=int(time.time()),
        body=service_response_bytes(
            request_bytes=service_request_bytes(method="POST", path=DISCOVERY, query="", body=body),
            response_body=response.content,
        ),
    )
    assert len(response.json()["scopes"]) == 1 and response.json()["next_cursor"]
    second_body = json.dumps({"limit": 1, "cursor": response.json()["next_cursor"]}).encode()
    second = await client.post(
        DISCOVERY, content=second_body, headers=discovery_headers(second_body)
    )
    assert second.status_code == 200 and second.json()["next_cursor"] is None
    assert {r["company_id"] for r in response.json()["scopes"] + second.json()["scopes"]} == {
        str(a),
        str(b),
    }
    wrong_limit = json.dumps({"limit": 2, "cursor": response.json()["next_cursor"]}).encode()
    assert (
        await client.post(DISCOVERY, content=wrong_limit, headers=discovery_headers(wrong_limit))
    ).status_code == 422
    for tenant, company in ((tenant_a, a), (tenant_b, b)):
        path = prefix(tenant, company)
        request = json.dumps({"request_id": str(uuid7())}).encode()
        result = await client.post(path, content=request, headers=headers("POST", path, request))
        assert result.status_code == 200, result.text
    with tenant_scope(tenant_a):
        row = await session.get(Company, a)
        assert row
        row.status = "suspended"
        await session.commit()
    path = prefix(tenant_a, a)
    request = json.dumps({"request_id": str(uuid7())}).encode()
    assert (
        await client.post(path, content=request, headers=headers("POST", path, request))
    ).status_code == 403
    response = await client.post(DISCOVERY, content=b"{}", headers=discovery_headers(b"{}"))
    assert response.json()["scopes"] == [{"tenant_id": str(tenant_b), "company_id": str(b)}]
    with tenant_scope(tenant_b):
        enrollment = (await session.scalars(select(CatalogSourceEnrollment))).one()
        enrollment.is_active = False
        await session.commit()
    path = prefix(tenant_b, b)
    assert (
        await client.post(path, content=request, headers=headers("POST", path, request))
    ).status_code == 403
    response = await client.post(DISCOVERY, content=b"{}", headers=discovery_headers(b"{}"))
    assert response.json()["scopes"] == []


def test_enrolled_credentials_must_explicitly_enable_dynamic_scope() -> None:
    secret = SecretStr("ephemeral-test-catalog-source-secret-0001")
    with pytest.raises(ValidationError):
        CatalogSourceCredential(secret=secret, scopes=())
    enabled = CatalogSourceCredential(secret=secret, scopes=(), allow_enrolled_companies=True)
    assert enabled.allow_enrolled_companies
    assert enabled.scopes == ()


async def test_operator_backfill_is_idempotent_and_preserves_disabled_enrollment(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    a, b = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_b):
        session.add(
            build_catalog_source_enrollment(tenant_id=tenant_b, company_id=b, is_active=False)
        )
        await session.commit()
    assert await backfill(session) == 1
    await session.rollback()
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(CatalogSourceEnrollment.id))) == 0
    assert await backfill(session) == 1
    await session.commit()
    assert await backfill(session) == 0
    with tenant_scope(tenant_a):
        enrolled = (await session.scalars(select(CatalogSourceEnrollment))).one()
        assert enrolled.company_id == a and enrolled.is_active
    with tenant_scope(tenant_b):
        assert not (await session.scalars(select(CatalogSourceEnrollment))).one().is_active
