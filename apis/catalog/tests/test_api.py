import base64
import hashlib
import hmac
import json
import time
import uuid

import httpx
import pytest
from billing_platform.ids import uuid7
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.config import Settings
from catalog.main import create_app
from catalog.metadata import MIGRATION_HEAD
from catalog.schemas.readiness import CatalogReadiness
from tests.conftest import ACTOR_SECRET


def headers(
    company: uuid.UUID,
    *,
    permission: str | list[str] = "item.read",
    tenant: uuid.UUID | None = None,
    user: uuid.UUID | None = None,
) -> dict[str, str]:
    body = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant or uuid7()),
            "user_id": str(user or uuid7()),
            "grants": [
                {
                    "permissions": [permission] if isinstance(permission, str) else permission,
                    "scope_type": "company",
                    "scope_id": str(company),
                    "valid_from": "2000-01-01",
                }
            ],
        }
    ).encode()
    return {
        "x-actor-context": base64.urlsafe_b64encode(body).rstrip(b"=").decode(),
        "x-actor-signature": hmac.new(ACTOR_SECRET.encode(), body, hashlib.sha256).hexdigest(),
    }


async def test_readiness_is_authorized_but_never_claims_unimplemented_features(
    client: httpx.AsyncClient,
) -> None:
    company = uuid7()
    response = await client.get(
        f"/v1/companies/{company}/catalog-readiness", headers=headers(company)
    )
    assert response.status_code == 200
    result = CatalogReadiness.model_validate(response.json())
    assert result.company_id == company and result.company_verified is False
    assert result.status == "not_ready"
    assert all(
        source.contract_version == (1 if source.owner == "identity" else None)
        for source in result.sources
    )
    assert all(
        capability.implemented
        == (
            capability.key
            in {
                "unit_and_pack_definitions",
                "product_definitions",
                "commercial_prices",
                "tax_definitions",
                "catalog_bulk_operations",
                # Definitions only. The location guards behind a non-Main retirement stay
                # a Billing source requirement, so this reads ready while that reads
                # unavailable — the two answer different questions.
                "stock_location_definitions",
                "manufacturing_operation_definitions",
                "manufacturing_route_definitions",
            }
        )
        for capability in result.capabilities
    )


async def test_authentication_scope_and_query_contract(client: httpx.AsyncClient) -> None:
    company = uuid7()
    route = f"/v1/companies/{company}/catalog-readiness"
    for supplied, expected in [
        ({}, 401),
        (headers(company, permission="item.create"), 403),
        (headers(uuid7()), 403),
        ({**headers(company), "x-actor-signature": "bad"}, 401),
    ]:
        result = await client.get(route, headers=supplied)
        assert result.status_code == expected
        assert set(result.json()) == {"error"}
    invalid = await client.get(route + "?enable_bom=true", headers=headers(company))
    assert invalid.status_code == 422
    malformed = await client.get(
        "/v1/companies/not-a-uuid/catalog-readiness", headers=headers(company)
    )
    assert malformed.status_code == 422
    assert "input" not in malformed.json()["error"]


async def test_probes_check_schema_and_version_without_exposing_details(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
) -> None:
    assert (await client.get("/health/live")).status_code == 200
    assert (await client.get("/health/ready")).status_code == 503
    async with engine.begin() as db:
        await db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        await db.execute(text("INSERT INTO alembic_version VALUES ('0005')"))
    assert (await client.get("/health/ready")).status_code == 503
    async with engine.begin() as db:
        await db.execute(
            text("UPDATE alembic_version SET version_num = :head"), {"head": MIGRATION_HEAD}
        )
    assert (await client.get("/health/ready")).json() == {"status": "ready"}
    async with engine.begin() as db:
        await db.execute(text("DROP TABLE state"))
    unavailable = await client.get("/health/ready")
    assert unavailable.status_code == 503
    assert "state" not in unavailable.text and "sql" not in unavailable.text.lower()


async def test_error_envelope_and_trace_sanitization(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    @app.get("/__test_failure", include_in_schema=False)
    async def failure() -> None:
        raise RuntimeError("SQL and private database details")

    response = await client.get("/__test_failure", headers={"x-trace-id": "a" * 32})
    assert response.status_code == 500
    assert response.json()["error"]["trace_id"] == "a" * 32
    assert "SQL" not in response.text
    missing = await client.get("/unknown", headers={"x-trace-id": "unsafe trace"})
    assert missing.status_code == 404
    assert missing.json()["error"]["trace_id"] == missing.headers["x-trace-id"]
    assert len(missing.headers["x-trace-id"]) == 32
    assert missing.headers["x-trace-id"] != "unsafe trace"


def test_settings_require_real_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite+aiosqlite://", actor_signing_secret=SecretStr("short"))
    monkeypatch.setenv("CATALOG_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("CATALOG_ACTOR_SIGNING_SECRET", ACTOR_SECRET)
    application = create_app()
    assert application.title == "Catalog API"


async def test_application_disposes_owned_engine() -> None:
    application = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(ACTOR_SECRET),
        )
    )
    async with application.router.lifespan_context(application):
        assert application.state.engine is not None
