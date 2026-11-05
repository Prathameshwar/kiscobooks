"""Ephemeral real Identity server for cross-process source contract tests only.

Input credentials arrive on stdin, bind loopback port zero, and keep all data in
memory. No production settings or database are read. The parent owns termination.
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from typing import Any

import uvicorn
from billing_platform.db import create_session_factory, tenant_scope
from billing_platform.ids import uuid7
from billing_platform.testing import make_sqlite_engine
from pydantic import SecretStr

from identity import models  # noqa: F401
from identity.config import CatalogSourceCredential, CatalogSourceScope, Settings
from identity.main import create_app
from tests.factories import (
    build_custom_field_definition,
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    seed_two_companies,
)


async def main() -> None:
    config: dict[str, Any] = json.loads(sys.stdin.readline())
    engine = await make_sqlite_engine()
    factory = create_session_factory(engine)
    tenant, other_tenant = uuid7(), uuid7()
    async with factory() as db:
        company, other_company = await seed_two_companies(db, tenant, other_tenant)
    user_id = uuid7()
    with tenant_scope(tenant):
        async with factory.begin() as db:
            db.add(build_user(tenant_id=tenant, user_id=user_id))
            role = build_role(tenant_id=tenant)
            db.add(role)
            await db.flush()
            for permission in (
                "unit.read",
                "unit.manage",
                "catalog.bulk.read",
                "catalog.bulk.manage",
                "catalog.bulk.commit",
                "item_group.read",
                "item_group.manage",
                "custom_field.manage",
            ):
                db.add(
                    build_role_permission(
                        tenant_id=tenant, role_id=role.id, permission_key=permission
                    )
                )
            db.add(
                build_custom_field_definition(
                    tenant_id=tenant,
                    company_id=company,
                    entity_type="catalog.item_group",
                    key="cf_note",
                    data_type="text",
                    is_searchable=True,
                )
            )
            db.add(
                build_role_assignment(
                    tenant_id=tenant,
                    role_id=role.id,
                    subject_id=user_id,
                    scope_type="company",
                    scope_id=company,
                )
            )
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(config["actor_secret"]),
            cursor_signing_secret=SecretStr(config["actor_secret"]),
            catalog_source_credentials={
                "current": CatalogSourceCredential(
                    secret=SecretStr(config["request_secret"]),
                    allow_actor_authorization=True,
                    scopes=(
                        CatalogSourceScope(tenant_id=tenant, company_id=company),
                        CatalogSourceScope(tenant_id=other_tenant, company_id=other_company),
                    ),
                )
            },
            catalog_source_response_secret=SecretStr(config["response_secret"]),
        )
    )
    await app.state.engine.dispose()
    app.state.engine = engine
    app.state.session_factory = factory
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    print(
        json.dumps(
            {
                "port": port,
                "user_id": str(user_id),
                "role_id": str(role.id),
                "tenant_id": str(tenant),
                "company_id": str(company),
                "other_tenant_id": str(other_tenant),
                "other_company_id": str(other_company),
            }
        ),
        flush=True,
    )
    try:
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        await server.serve(sockets=[listener])
    finally:
        listener.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
