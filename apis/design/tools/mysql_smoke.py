"""Exercise the design API against a real MySQL schema, not SQLite.

    DESIGN_TEST_MYSQL_SERVER_URL=mysql+asyncmy://user:pass@127.0.0.1:3306 \
        uv run python tools/mysql_smoke.py

The suites run on in-memory SQLite, which is fast and isolated but proves nothing about
MySQL's dialect — and three things here are dialect behaviour: the `live_code` generated
column that gives one live code per company while archived rows keep theirs, `DECIMAL(19,4)`
round-tripping as `Decimal`, and `JSON` columns holding the layout tree. This tool applies
the migrations to a throwaway schema, drives the HTTP surface through it, and drops only
the schema it created.

The server URL must name a loopback development server and carry no database name.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from design.config import Settings
from design.main import create_app
from tests.conftest import canvas

ROOT = Path(__file__).resolve().parents[3]


def _server_url() -> str:
    url = os.environ.get("DESIGN_TEST_MYSQL_SERVER_URL")
    if not url:
        raise SystemExit("DESIGN_TEST_MYSQL_SERVER_URL must name a loopback MySQL server")
    parsed = make_url(url)
    if parsed.database:
        raise SystemExit("DESIGN_TEST_MYSQL_SERVER_URL must not name a database")
    if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("refusing to run against a non-loopback server")
    return url


def _headers(tenant: uuid.UUID, company: uuid.UUID, secret: str) -> dict[str, str]:
    import base64
    import hashlib
    import hmac
    import json
    import time

    from tests.conftest import ALL_PERMISSIONS

    body = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant),
            "user_id": str(uuid.uuid4()),
            "grants": [
                {
                    "permissions": list(ALL_PERMISSIONS),
                    "scope_type": "company",
                    "scope_id": str(company),
                    "valid_from": "2000-01-01",
                }
            ],
        }
    ).encode()
    return {
        "x-actor-context": base64.urlsafe_b64encode(body).rstrip(b"=").decode(),
        "x-actor-signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
    }


async def _drive(url: str, secret: str) -> None:
    app = create_app(
        Settings(
            database_url=url,
            actor_signing_secret=SecretStr(secret),
            cursor_signing_secret=SecretStr(secret),
        )
    )
    tenant, company = uuid.uuid4(), uuid.uuid4()
    auth = _headers(tenant, company, secret)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://design.test") as api:
            ready = await api.get("/health/ready")
            assert ready.status_code == 200, ready.text

            created = await api.post(
                f"/v1/companies/{company}/templates",
                json={
                    "name": "MySQL smoke",
                    "code": "mysql-smoke",
                    "paper_size": "CUSTOM",
                    "page_width_mm": "210.0000",
                    "page_height_mm": "297.0000",
                    "initial_canvas": canvas(),
                },
                headers=auth,
            )
            assert created.status_code == 201, created.text
            template: dict[str, Any] = created.json()
            # DECIMAL(19,4) must round-trip exactly, not through a float.
            assert Decimal(template["page_width_mm"]) == Decimal("210")

            published = await api.post(
                f"/v1/companies/{company}/templates/{template['id']}"
                f"/versions/{template['initial_version_id']}/publish",
                headers=auth,
            )
            assert published.status_code == 200, published.text

            resolved = await api.post(
                f"/v1/companies/{company}/resolve",
                json={"voucher_kind": "SALES_INVOICE"},
                headers=auth,
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["layout_definition"]["sections"][0]["type"] == "HEADER"

            archived = await api.delete(
                f"/v1/companies/{company}/templates/{template['id']}", headers=auth
            )
            assert archived.status_code == 204, archived.text

            # The generated column releases the code: this is the behaviour SQLite cannot
            # prove for MySQL's "many NULLs in a unique index".
            again = await api.post(
                f"/v1/companies/{company}/templates",
                json={"name": "MySQL smoke", "code": "mysql-smoke"},
                headers=auth,
            )
            assert again.status_code == 201, again.text
            duplicate = await api.post(
                f"/v1/companies/{company}/templates",
                json={"name": "MySQL smoke", "code": "mysql-smoke"},
                headers=auth,
            )
            assert duplicate.status_code == 409, duplicate.text
    await app.state.engine.dispose()


async def _administer(server: str, statement: str) -> None:
    admin = create_async_engine(server, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await admin.dispose()


def main() -> None:
    """Each step gets its own loop: Alembic's env.py runs ``asyncio.run`` itself."""
    server = _server_url()
    schema = f"design_smoke_{uuid.uuid4().hex[:12]}"
    secret = secrets.token_hex(32)  # ephemeral: this process signs and verifies it
    url = f"{server.rstrip('/')}/{schema}"
    asyncio.run(
        _administer(
            server,
            f"CREATE DATABASE {schema} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
        )
    )
    try:
        config = Config(str(ROOT / "dbs" / "design" / "alembic.ini"))
        config.attributes["database_url"] = url
        command.upgrade(config, "head")
        asyncio.run(_drive(url, secret))
        print(f"design MySQL smoke passed on {schema}")
    finally:
        asyncio.run(_administer(server, f"DROP DATABASE IF EXISTS {schema}"))


if __name__ == "__main__":
    main()
