"""Customer-pricing effective read HTTP contract."""

import datetime as dt
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CompanyPricingPolicy,
    CustomerPricingProjection,
    CustomerTypeProjection,
    PriceLevel,
    PriceLevelAssignment,
    PriceLevelAssignmentScope,
)
from tests.test_api import headers
from tests.test_classification_api import setup_source


async def _seed_default_pricing(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
) -> uuid.UUID:
    """Create a price_level plus a company_pricing_policy pointing at it."""
    with tenant_scope(tenant):
        async with factory.begin() as db:
            level = PriceLevel(
                id=uuid7(),
                tenant_id=tenant,
                company_id=company,
                code="PRICE1",
                name="Standard",
                ordinal=1,
                is_active=True,
                row_version=1,
            )
            db.add(level)
            await db.flush()
            db.add(
                CompanyPricingPolicy(
                    id=uuid7(),
                    tenant_id=tenant,
                    company_id=company,
                    default_level_id=level.id,
                    missing_price_policy="ERROR",
                    fallback_level_id=None,
                    purchase_plan_id=None,
                    sale_unit_mode="EXPLICIT_ONLY",
                    purchase_unit_mode="EXPLICIT_ONLY",
                    valid_from=dt.date(2020, 1, 1),
                    valid_to=None,
                    row_version=1,
                )
            )
            return level.id


async def test_effective_read_returns_company_default(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    default_level = await _seed_default_pricing(factory, tenant_a, company)
    auth = headers(company, tenant=tenant_a, user=user, permission="customer_pricing.read")
    party = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(CustomerPricingProjection(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                source_id=uuid7(), source_version=1, party_id=party,
                customer_type_code=None, valid_from=dt.date(2020, 1, 1),
                valid_to=None, is_active=True,
            ))
    response = await client.get(
        f"/v1/companies/{company}/customer-pricing/effective",
        headers=auth,
        params={"party_id": str(party), "as_of": "2026-06-01"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert uuid.UUID(body["price_level_id"]) == default_level
    assert body["chain"] == [{"kind": "company", "ref": "default"}]


async def test_effective_read_returns_customer_type_when_matched(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    await _seed_default_pricing(factory, tenant_a, company)
    party = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            wholesale_level = PriceLevel(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=company,
                code="WHOLESALE",
                name="Wholesale",
                ordinal=2,
                is_active=True,
                row_version=1,
            )
            db.add(wholesale_level)
            db.add(CustomerTypeProjection(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                source_id=uuid7(), source_version=1, code="WHOLESALE",
                display_name="Wholesale", parent_code=None, is_active=True,
            ))
            await db.flush()
            db.add(
                CustomerPricingProjection(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    source_id=uuid7(),
                    source_version=1,
                    party_id=party,
                    customer_type_code="WHOLESALE",
                    valid_from=dt.date(2020, 1, 1),
                    valid_to=None,
                    is_active=True,
                )
            )
            scope = PriceLevelAssignmentScope(
                id=uuid7(),
                tenant_id=tenant_a,
                company_id=company,
                subject_kind="PRICING_TYPE",
                customer_ref=None,
                pricing_type_ref="WHOLESALE",
                row_version=1,
            )
            db.add(scope)
            await db.flush()
            db.add(
                PriceLevelAssignment(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    scope_id=scope.id,
                    price_level_id=wholesale_level.id,
                    valid_from=dt.date(2020, 1, 1),
                    valid_to=None,
                    row_version=1,
                )
            )
            expected_level = wholesale_level.id
    auth = headers(company, tenant=tenant_a, user=user, permission="customer_pricing.read")
    response = await client.get(
        f"/v1/companies/{company}/customer-pricing/effective",
        headers=auth,
        params={"party_id": str(party), "as_of": "2026-06-01"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert uuid.UUID(body["price_level_id"]) == expected_level
    assert body["chain"] == [{"kind": "customer_type", "ref": "WHOLESALE"}]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            customer_type = await db.scalar(
                select(CustomerTypeProjection).where(
                    CustomerTypeProjection.company_id == company,
                    CustomerTypeProjection.code == "WHOLESALE",
                )
            )
            assert customer_type is not None
            customer_type.is_active = False
    inactive = await client.get(
        f"/v1/companies/{company}/customer-pricing/effective",
        headers=auth,
        params={"party_id": str(party), "as_of": "2026-06-01"},
    )
    assert inactive.status_code == 422


async def test_effective_read_denies_unauthenticated_and_underprivileged(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    await _seed_default_pricing(factory, tenant_a, company)
    route = f"/v1/companies/{company}/customer-pricing/effective"
    params = {"party_id": str(uuid7()), "as_of": "2026-06-01"}
    unauth = await client.get(route, params=params)
    assert unauth.status_code == 401
    read_only = headers(company, tenant=tenant_a, user=user, permission="item.read")
    forbidden = await client.get(route, headers=read_only, params=params)
    assert forbidden.status_code == 403


async def test_effective_read_refuses_unconfigured_default_as_422(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    """No company pricing policy at all → the resolver refuses and the API returns 422.

    The route treats an unconfigured company default as bad input, not as a
    conflict — the caller cannot proceed without a real default configured
    first, so they need to fix the setup rather than retry the request.
    """
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    auth = headers(company, tenant=tenant_a, user=user, permission="customer_pricing.read")
    response = await client.get(
        f"/v1/companies/{company}/customer-pricing/effective",
        headers=auth,
        params={"party_id": str(uuid7()), "as_of": "2026-06-01"},
    )
    assert response.status_code == 422
    assert "company default" in response.json()["error"]["message"].lower()


async def test_effective_read_refuses_missing_buyer_source_instead_of_defaulting(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    await _seed_default_pricing(factory, tenant_a, company)
    response = await client.get(
        f"/v1/companies/{company}/customer-pricing/effective",
        headers=headers(company, tenant=tenant_a, user=user, permission="customer_pricing.read"),
        params={"party_id": str(uuid7()), "as_of": "2026-06-01"},
    )
    assert response.status_code == 422
    assert "membership" in response.json()["error"]["message"].lower()


async def test_effective_read_refuses_expired_company_policy(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    await _seed_default_pricing(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            policy = await db.scalar(
                select(CompanyPricingPolicy).where(CompanyPricingPolicy.company_id == company)
            )
            assert policy is not None
            policy.valid_to = dt.date(2026, 5, 31)
    response = await client.get(
        f"/v1/companies/{company}/customer-pricing/effective",
        headers=headers(company, tenant=tenant_a, user=user, permission="customer_pricing.read"),
        params={"party_id": str(uuid7()), "as_of": "2026-06-01"},
    )
    assert response.status_code == 422
    assert "company default" in response.json()["error"]["message"].lower()
