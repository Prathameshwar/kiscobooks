"""Production-dialect races for the first-use reservation and custom text index."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import delete, select

from identity.config import CatalogSourceCredential, CatalogSourceScope, Settings
from identity.install import install_identity
from identity.main import create_app
from identity.models import Company, PostingReservation
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET, actor_headers, grant
from tests.factories import build_company, build_tenant, build_user
from tests.test_gap_posting import SECRET, signed


@pytest.mark.mysql
def test_real_mysql_reservation_vs_settings_race(mysql_url: str) -> None:
    install_identity(mysql_url)

    async def exercise() -> None:
        tenant, company, user = uuid7(), uuid7(), uuid7()
        settings = Settings(
            database_url=mysql_url,
            actor_signing_secret=SecretStr(ACTOR_SECRET),
            cursor_signing_secret=SecretStr(CURSOR_SECRET),
            billing_reservation_credentials={
                "test": CatalogSourceCredential(
                    secret=SecretStr(SECRET.decode()),
                    scopes=(CatalogSourceScope(tenant_id=tenant, company_id=company),),
                )
            },
            billing_reservation_response_secret=SecretStr("response-billing-ephemeral-test-key-32"),
        )
        app = create_app(settings)
        try:
            with tenant_scope(tenant):
                async with app.state.session_factory() as db, db.begin():
                    db.add(build_tenant(tenant_id=tenant, slug="gap-" + tenant.hex))
                    await db.flush()
                    db.add(build_company(tenant_id=tenant, company_id=company, state_code="IN-MH"))
                    db.add(build_user(tenant_id=tenant, user_id=user))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://identity.test"
            ) as client:
                root = f"/internal/v1/tenants/{tenant}/companies/{company}/posting"
                config = await client.get(
                    root + "/configuration", headers=signed("GET", root + "/configuration")
                )
                assert config.status_code == 200, config.text
                operation = uuid7()
                body = json.dumps(
                    {
                        "operation_id": str(operation),
                        "actor_user_id": str(user),
                        "configuration_hash": config.json()["configuration_hash"],
                        "features": [],
                    }
                ).encode()
                path = root + "/reservations"
                headers = actor_headers(
                    tenant_id=tenant, user_id=user, grants=[grant(["company.update"])]
                )
                results = await asyncio.gather(
                    client.post(path, content=body, headers=signed("POST", path, body, "reserve")),
                    client.patch(
                        f"/v1/companies/{company}", headers=headers, json={"amount_precision": 3}
                    ),
                )
                assert sorted(r.status_code for r in results) == [200, 409], [
                    (r.status_code, r.text) for r in results
                ]
                with tenant_scope(tenant):
                    async with app.state.session_factory() as db:
                        row = await db.get(Company, company)
                        reservation = await db.scalar(
                            select(PostingReservation).where(
                                PostingReservation.company_id == company
                            )
                        )
                        assert row.first_posted_at is None
                        assert (row.amount_precision == 3 and reservation is None) or (
                            row.amount_precision == 2 and reservation is not None
                        )
        finally:
            # This test owns this generated tenant. Remove its synthetic freeze so
            # other migration tests can exercise the legitimate empty-table downgrade.
            with tenant_scope(tenant):
                async with app.state.session_factory() as db, db.begin():
                    await db.execute(
                        delete(PostingReservation).where(PostingReservation.company_id == company)
                    )
            await app.state.engine.dispose()

    asyncio.run(exercise())
