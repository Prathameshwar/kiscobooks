"""Authentication and the probes: 401 before anything else happens."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from billing_platform.ids import uuid7
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

from design.config import Settings
from tests.conftest import canvas


@pytest.mark.asyncio
async def test_live_probe_is_public(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_probe_reports_a_schema_without_its_migration_head(
    client: httpx.AsyncClient,
) -> None:
    """The SQLite test schema has the tables but no ``alembic_version`` row.

    A probe that answered "ready" here would be exactly the lie it exists to prevent, so
    503 is the correct, truthful answer.
    """
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"


@pytest.mark.asyncio
async def test_unauthenticated_request_is_401(
    client: httpx.AsyncClient, company_id: uuid.UUID
) -> None:
    response = await client.get(f"/v1/companies/{company_id}/templates")
    assert response.status_code == 401
    body = response.json()
    assert "error" in body and "trace" not in response.text.lower()


@pytest.mark.asyncio
async def test_forged_signature_is_401(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    headers = signed_headers(tenant_id, company_id)
    headers["x-actor-signature"] = "0" * 64
    response = await client.get(f"/v1/companies/{company_id}/templates", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unsigned_test_headers_are_not_a_credential(
    client: httpx.AsyncClient, company_id: uuid.UUID, tenant_id: uuid.UUID
) -> None:
    """The removed bypass, as a regression test."""
    response = await client.get(
        f"/v1/companies/{company_id}/templates",
        headers={"x-test-tenant-id": str(tenant_id), "x-test-user-id": str(uuid7())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_support_session_cannot_write(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    support = signed_headers(tenant_id, company_id, impersonated=True)
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={"name": "support", "code": "support", "initial_canvas": canvas()},
        headers=support,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tenant_wide_company_path_is_rejected(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    """``company_id`` of all zeroes would read as "every company"."""
    sentinel = uuid.UUID(int=0)
    response = await client.get(
        f"/v1/companies/{sentinel}/templates",
        headers=signed_headers(tenant_id, sentinel, tenant_wide=True),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_query_parameters_are_rejected(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"/v1/companies/{company_id}/templates?limit=5&limit=200", headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_oversized_body_is_413(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    payload = {"name": "big", "code": "big", "description": "x" * 400}
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        content=b'{"padding": "' + b"y" * 6_000_000 + b'"}',
        headers={**auth_headers, "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert payload  # the shape above is only here to document the normal case


@pytest.mark.asyncio
async def test_responses_carry_no_store_and_nosniff(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.get(f"/v1/companies/{company_id}/templates", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_settings_refuse_a_weak_signing_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr("short"),
            cursor_signing_secret=SecretStr("x" * 32),
        )


def test_settings_have_no_default_credentials() -> None:
    """A default database URL or signing secret is a credential in the repository."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings keyword


def test_app_builds_without_a_database(app: FastAPI) -> None:
    assert app.title == "Invoice Designer API"
