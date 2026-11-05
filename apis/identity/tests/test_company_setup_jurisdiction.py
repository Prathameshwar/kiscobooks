"""Changing country must preserve all kinds of statutory history."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    build_company_statutory_id,
    build_company_tax_registration,
    build_country,
    build_state,
    seed_two_companies,
)
from tests.test_api_companies import _admin_headers


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", ["none", "tax", "statutory_id"])
async def test_country_change_only_before_statutory_records_exist(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    existing: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        session.add(build_country("GB"))
        await session.flush()
        session.add(build_state("GB-ENG", "GB"))
        if existing == "tax":
            session.add(build_company_tax_registration(tenant_id=tenant_a, company_id=company))
        if existing == "statutory_id":
            session.add(build_company_statutory_id(tenant_id=tenant_a, company_id=company))
        await session.commit()
    response = await client.patch(
        f"/v1/companies/{company}",
        headers=_admin_headers(tenant_a),
        json={"country_code": "GB", "state_code": "GB-ENG", "default_tax_system": "vat_gb"},
    )
    assert response.status_code == (200 if existing == "none" else 422), response.text
    detail = await client.get(f"/v1/companies/{company}", headers=_admin_headers(tenant_a))
    assert detail.json()["country_code"] == ("GB" if existing == "none" else "IN")
