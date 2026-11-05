"""Company setup against real migrated MySQL, including the parent-row lock."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import func, select

from identity.config import Settings
from identity.install import install_identity
from identity.main import create_app
from identity.models import Company, CompanyLicence
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET
from tests.factories import build_tenant
from tests.test_api_companies import _valid_company_body
from tests.test_company_setup_review import headers, licence_body


@pytest.mark.mysql
def test_seeded_company_setup_and_concurrent_country_change(mysql_url: str) -> None:
    install_identity(mysql_url)
    # Reinstalling must preserve global reference choices and existing identities.
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
            with unfiltered():
                async with app.state.session_factory() as session:
                    session.add(build_tenant(tenant_id=tenant, slug=f"setup-{tenant.hex[:12]}"))
                    await session.commit()
            auth = headers(
                tenant, "company.create", "company.read", "company.update", "company.licence.manage"
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://identity.test"
            ) as client:
                countries = await client.get("/v1/reference/countries", headers=auth)
                assert countries.status_code == 200 and len(countries.json()) > 200
                states = await client.get("/v1/reference/countries/IN/states", headers=auth)
                state = next(s["code"] for s in states.json() if s["code"] == "IN-MH")
                body = {**_valid_company_body(), "state_code": state, "reporting_currency": "USD"}
                created = await client.post("/v1/companies", json=body, headers=auth)
                assert created.status_code == 201, created.text
                company = created.json()["id"]
                for kind in ["drug_licence_20", "drug_licence_21"]:
                    saved = await client.post(
                        f"/v1/companies/{company}/licences",
                        headers=auth,
                        json=licence_body(kind=kind, number=kind),
                    )
                    assert saved.status_code == 201, saved.text
                invalid = await client.patch(
                    f"/v1/companies/{company}", headers=auth, json={"reporting_currency": "ZZZ"}
                )
                assert invalid.status_code == 422
                detail = await client.get(f"/v1/companies/{company}", headers=auth)
                assert detail.json()["reporting_currency"] == "USD"
                licences = await client.get(f"/v1/companies/{company}/licences", headers=auth)
                assert len(licences.json()["items"]) == 2

                # Race a pre-posting country change against the first licence.
                # Whichever takes the parent lock first wins; the other must fail.
                created = await client.post(
                    "/v1/companies", headers=auth, json={**body, "code": "RACE"}
                )
                assert created.status_code == 201, created.text
                target = created.json()["id"]
                uk_states = await client.get("/v1/reference/countries/GB/states", headers=auth)
                state_gb = next(s["code"] for s in uk_states.json() if s["code"] == "GB-ENG")
                outcomes = await asyncio.gather(
                    client.patch(
                        f"/v1/companies/{target}",
                        headers=auth,
                        json={
                            "country_code": "GB",
                            "state_code": state_gb,
                            "default_tax_system": "vat_gb",
                        },
                    ),
                    client.post(
                        f"/v1/companies/{target}/licences",
                        headers=auth,
                        json=licence_body(kind="drug_licence_20"),
                    ),
                )
                assert sorted(r.status_code for r in outcomes) in ([200, 422], [201, 422]), [
                    (r.status_code, r.text) for r in outcomes
                ]
                with tenant_scope(tenant):
                    async with app.state.session_factory() as session:
                        row = await session.get(Company, uuid.UUID(target))
                        assert row is not None
                        count = await session.scalar(
                            select(func.count(CompanyLicence.id)).where(
                                CompanyLicence.company_id == row.id
                            )
                        )
                        assert (row.country_code, count) in [("GB", 0), ("IN", 1)]
        finally:
            await app.state.engine.dispose()

    asyncio.run(exercise())
