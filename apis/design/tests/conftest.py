"""Isolated databases and signed gateway contexts for the design suites.

The app runs against an in-memory SQLite schema built from the models with foreign keys
enforced (``billing_platform.testing``), and every request carries a **signed** actor
context, built the way Identity's gateway builds one. There is no unsigned path in the
service, so there is none here: a suite that authenticated differently from production
would be green about the wrong code.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from billing_platform.ids import uuid7
from billing_platform.testing import engine  # noqa: F401
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from design import models  # noqa: F401  registers the tables before the engine fixture runs
from design.config import Settings
from design.main import create_app

#: Every design permission, for the common case where the test is not about authorization.
ALL_PERMISSIONS: tuple[str, ...] = (
    "design.template.read",
    "design.template.manage",
    "design.template.publish",
    "design.assignment.read",
    "design.assignment.manage",
    "design.asset.read",
    "design.asset.manage",
    "design.component.read",
    "design.component.manage",
    "design.render.read",
    "design.render.record",
)


@pytest.fixture
def signing_secret() -> bytes:
    return secrets.token_hex(32).encode()


@pytest.fixture
def app(engine: AsyncEngine, signing_secret: bytes) -> FastAPI:  # noqa: F811
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(signing_secret.decode()),
            cursor_signing_secret=SecretStr(secrets.token_hex(32)),
        ),
        engine=engine,
    )


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid7()


@pytest.fixture
def company_id() -> uuid.UUID:
    return uuid7()


@pytest.fixture
def signed_headers(signing_secret: bytes) -> Callable[..., dict[str, str]]:
    """Mint a signed actor context.

    ``tenant_wide=True`` grants at tenant scope, which is what a shared template requires;
    ``impersonated=True`` mints a support context, whose grants the platform decoder
    narrows to reads.
    """

    def build(
        tenant_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
        *,
        permissions: tuple[str, ...] = ALL_PERMISSIONS,
        tenant_wide: bool = False,
        user_id: uuid.UUID | None = None,
        impersonated: bool = False,
    ) -> dict[str, str]:
        subject = user_id or uuid7()
        context: dict[str, object] = {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant_id),
            "user_id": str(subject),
            "grants": [
                {
                    "permissions": list(permissions),
                    "scope_type": "tenant" if tenant_wide else "company",
                    "scope_id": None if tenant_wide else str(company_id),
                    "valid_from": "2000-01-01",
                }
            ],
        }
        if impersonated:
            context |= {
                "actor_user_id": str(uuid7()),
                "impersonation_id": str(uuid7()),
                "impersonation_expires_at": int(time.time()) + 600,
            }
        body = json.dumps(context).encode()
        return {
            "x-actor-context": base64.urlsafe_b64encode(body).rstrip(b"=").decode(),
            "x-actor-signature": hmac.new(signing_secret, body, hashlib.sha256).hexdigest(),
        }

    return build


@pytest.fixture
def auth_headers(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> dict[str, str]:
    return signed_headers(tenant_id, company_id)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://design.test",
        ) as connection:
            yield connection


# ---------------------------------------------------------------------------
# Builders. Kept here rather than in each module: a layout that validates is a
# non-trivial literal, and three copies of it would drift.
# ---------------------------------------------------------------------------


def canvas(
    *,
    element_id: str = "el_title",
    asset_id: str | None = None,
    component_code: str | None = None,
    content: str = "TAX INVOICE",
) -> dict[str, object]:
    element: dict[str, object] = {
        "id": element_id,
        "type": "TEXT",
        "x": 10.0,
        "y": 10.0,
        "width": 100.0,
        "height": 20.0,
        "content": content,
    }
    if asset_id is not None:
        element |= {"type": "IMAGE", "asset_id": asset_id}
    section: dict[str, object] = {
        "id": "sec_header",
        "type": "HEADER",
        "elements": [element],
    }
    if component_code is not None:
        section |= {"component_code": component_code}
    return {"schema_version": "1.0.0", "sections": [section]}


async def make_template(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    *,
    code: str = "std-invoice",
    with_canvas: bool = True,
    tenant_wide: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {"name": code, "code": code, "is_tenant_wide": tenant_wide}
    if with_canvas:
        payload["initial_canvas"] = canvas()
    response = await client.post(f"/v1/companies/{company}/templates", json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def publish_template(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    template: dict[str, object],
    version_id: object | None = None,
) -> dict[str, object]:
    target = version_id or template["initial_version_id"]
    response = await client.post(
        f"/v1/companies/{company}/templates/{template['id']}/versions/{target}/publish",
        headers=auth,
    )
    assert response.status_code == 200, response.text
    return dict(response.json())
