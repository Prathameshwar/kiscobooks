"""Configuration actions persist, reject stale/inactive writes and keep audit truthful."""

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company, Outbox
from tests.api_support import actor_headers, grant
from tests.factories import seed_two_companies
from tests.test_api_companies import _admin_headers

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("status", ["suspended", "closed"])
@pytest.mark.parametrize("action", ["enable", "disable"])
async def test_inactive_company_features_are_readable_but_not_writable(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    status: str,
    action: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        assert row is not None
        row.status = status
        await session.commit()
    headers = _admin_headers(tenant_a)
    response = await client.post(
        f"/v1/companies/{company}/features/budgets/{action}", headers=headers
    )
    assert response.status_code == 409, response.text
    listing = await client.get(f"/v1/companies/{company}/features", headers=headers)
    assert listing.status_code == 200
    assert "budgets" not in listing.json()["enabled"]


async def test_reviewed_feature_changes_advance_version_and_refuse_stale_review(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    detail = await client.get(f"/v1/companies/{company}/setup-readiness", headers=headers)
    stamp = detail.json()["company_updated_at"]
    enabled = await client.post(
        f"/v1/companies/{company}/features/budgets/enable",
        headers=headers,
        json={"expected_updated_at": stamp, "reason": "Enable planning"},
    )
    assert enabled.status_code == 200, enabled.text
    latest = await client.get(f"/v1/companies/{company}/setup-readiness", headers=headers)
    assert latest.json()["company_updated_at"] != stamp
    stale = await client.post(
        f"/v1/companies/{company}/features/budgets/disable",
        headers=headers,
        json={"expected_updated_at": stamp, "reason": "Reviewed removal"},
    )
    assert stale.status_code == 409, stale.text
    disabled = await client.post(
        f"/v1/companies/{company}/features/budgets/disable",
        headers=headers,
        json={"expected_updated_at": latest.json()["company_updated_at"]},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["is_enabled"] is False


async def test_repeated_enable_does_not_invent_a_change_or_audit_event(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    for _ in range(2):
        response = await client.post(
            f"/v1/companies/{company}/features/budgets/enable", headers=headers
        )
        assert response.status_code == 200
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "company.feature_enabled")
            )
        )
        assert len(events) == 1


@pytest.mark.parametrize("action", ["enable", "disable"])
@pytest.mark.parametrize(
    "authority,status",
    [("anonymous", 401), ("none", 403), ("wrong_company", 403), ("wrong_tenant", 404)],
)
async def test_feature_writes_require_endpoint_and_company_scope(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    action: str,
    authority: str,
    status: int,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = (
        {}
        if authority == "anonymous"
        else actor_headers(
            tenant_id=tenant_b if authority == "wrong_tenant" else tenant_a,
            user_id=uuid7(),
            grants=[]
            if authority == "none"
            else [
                grant(
                    ["company.update"],
                    scope_type="company" if authority == "wrong_company" else "tenant",
                    scope_id=uuid7() if authority == "wrong_company" else None,
                )
            ],
        )
    )
    response = await client.post(
        f"/v1/companies/{company}/features/budgets/{action}", headers=headers
    )
    assert response.status_code == status, response.text


@pytest.mark.parametrize("reason", ["bad\nreason", "bad\x00reason", "x" * 201])
async def test_feature_reason_validation_prevents_configuration_changes(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    reason: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    response = await client.post(
        f"/v1/companies/{company}/features/budgets/enable", headers=headers, json={"reason": reason}
    )
    assert response.status_code == 422
    listing = await client.get(f"/v1/companies/{company}/features", headers=headers)
    assert "budgets" not in listing.json()["enabled"]
