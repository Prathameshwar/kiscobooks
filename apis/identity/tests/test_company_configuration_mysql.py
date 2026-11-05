"""Reviewed company changes serialize against a real migrated MySQL parent row."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import func, select

from identity.config import Settings
from identity.install import install_identity
from identity.main import create_app
from identity.models import Outbox
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET
from tests.factories import build_tenant
from tests.test_api_companies import _admin_headers, _valid_company_body


@pytest.mark.mysql
def test_reviewed_feature_writes_serialize_and_invalidate_an_old_profile_review(
    mysql_url: str,
) -> None:
    install_identity(mysql_url)

    async def exercise() -> None:
        app = create_app(
            Settings(
                database_url=mysql_url,
                actor_signing_secret=SecretStr(ACTOR_SECRET),
                cursor_signing_secret=SecretStr(CURSOR_SECRET),
            )
        )
        tenant = uuid7()
        try:
            with tenant_scope(tenant):
                async with app.state.session_factory() as db, db.begin():
                    db.add(build_tenant(tenant_id=tenant, slug="config-" + tenant.hex))
            auth = _admin_headers(tenant)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://identity.test"
            ) as client:
                created = await client.post(
                    "/v1/companies",
                    headers=auth,
                    json={**_valid_company_body(), "state_code": "IN-MH"},
                )
                assert created.status_code == 201, created.text
                company = created.json()["id"]
                base = f"/v1/companies/{company}"
                before = (await client.get(base + "/setup-readiness", headers=auth)).json()
                review = {"expected_updated_at": before["company_updated_at"], "reason": "Reviewed"}
                outcomes = await asyncio.gather(
                    client.post(base + "/features/budgets/enable", headers=auth, json=review),
                    client.post(base + "/features/credit_limits/enable", headers=auth, json=review),
                )
                assert sorted(response.status_code for response in outcomes) == [200, 409], [
                    (response.status_code, response.text) for response in outcomes
                ]
                winner = next(
                    response.json()["feature_key"]
                    for response in outcomes
                    if response.status_code == 200
                )
                after = (await client.get(base + "/setup-readiness", headers=auth)).json()
                assert after["company_updated_at"] != before["company_updated_at"]
                enabled = [
                    row["feature_key"] for row in after["features"] if row["state"] == "ENABLED"
                ]
                assert [key for key in enabled if key in {"budgets", "credit_limits"}] == [winner]
                stale_profile = await client.patch(
                    base,
                    headers=auth,
                    json={
                        "expected_updated_at": before["company_updated_at"],
                        "display_name": "Stale company review",
                    },
                )
                assert stale_profile.status_code == 409, stale_profile.text
                repeat = await client.post(
                    base + f"/features/{winner}/enable",
                    headers=auth,
                    json={"expected_updated_at": after["company_updated_at"]},
                )
                assert repeat.status_code == 200, repeat.text
                repeated = (await client.get(base + "/setup-readiness", headers=auth)).json()
                assert repeated["company_updated_at"] == after["company_updated_at"]
                with tenant_scope(tenant):
                    async with app.state.session_factory() as db:
                        count = await db.scalar(
                            select(func.count(Outbox.id)).where(
                                Outbox.aggregate_id == uuid.UUID(company),
                                Outbox.event_type == "company.feature_enabled",
                            )
                        )
                        assert count == 1
        finally:
            await app.state.engine.dispose()

    asyncio.run(exercise())
