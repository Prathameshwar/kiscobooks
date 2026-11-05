"""Buyer-type price levels must affect ordinary item price lookup."""

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CustomerPricingProjection,
    CustomerTypeProjection,
    PriceLevelAssignment,
    PriceLevelAssignmentScope,
)
from tests.pricing_factories import create, foundation, publish_price, setup_pricing
from tests.test_api import headers
from tests.test_pricing_levels_units import feature
from tests.test_pricing_resolution import query, resolve

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_buyer_type_selects_its_level_without_administrative_override(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await feature(factory, tenant_a, company, ids["actor_user"])
    setup = await foundation(client, root, auth, ids)
    await publish_price(client, root, auth, setup, amount="100")
    levels = (await client.get(root + "/price-levels", headers=auth)).json()["items"]
    wholesale_level = levels[1]["id"]
    plan = await create(
        client, root, auth, "/price-plans",
        {
            "code": "WHOLESALE", "name": "Wholesale", "purpose": "SALE",
            "price_level_id": wholesale_level, "currency": "INR", "tax_basis": "EXCLUSIVE",
        },
    )
    series = await create(
        client, root, auth, "/price-series",
        {
            "plan_id": plan["id"], "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    await publish_price(client, root, auth, {**setup, "series": series}, amount="90")
    buyer = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(CustomerTypeProjection(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                source_id=uuid7(), source_version=1, code="WHOLESALE",
                display_name="Wholesale", parent_code=None, is_active=True,
            ))
            db.add(CustomerPricingProjection(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                source_id=uuid7(), source_version=1, party_id=buyer,
                customer_type_code="WHOLESALE", valid_from=dt.date(2090, 1, 1),
                valid_to=None, is_active=True,
            ))
            scope = PriceLevelAssignmentScope(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                subject_kind="PRICING_TYPE", customer_ref=None,
                pricing_type_ref="WHOLESALE", row_version=1,
            )
            db.add(scope)
            await db.flush()
            db.add(PriceLevelAssignment(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                scope_id=scope.id, price_level_id=uuid.UUID(wholesale_level),
                valid_from=dt.date(2090, 1, 1), valid_to=None, row_version=1,
            ))
    standard = await resolve(client, root, auth, ids)
    selected = await resolve(client, root, auth, ids, party_id=str(buyer))
    assert standard["amount"] == "100.0000"
    assert selected["amount"] == "90.0000"
    assert selected["price_level_id"] == wholesale_level
    assert selected["buyer_price_level_id"] == wholesale_level
    assert selected["buyer_pricing_chain"] == [{"kind": "customer_type", "ref": "WHOLESALE"}]
    assert len(selected["source_ids"]) > len(standard["source_ids"])
    limited = headers(
        company, tenant=tenant_a, user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"customer_pricing.read"}),
    )
    forbidden = await client.post(
        root + "/prices/resolve", headers=limited,
        json=query(ids, party_id=str(buyer)),
    )
    assert forbidden.status_code == 403
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            scope = PriceLevelAssignmentScope(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                subject_kind="CUSTOMER", customer_ref=buyer,
                pricing_type_ref=None, row_version=1,
            )
            db.add(scope)
            await db.flush()
            db.add(PriceLevelAssignment(
                id=uuid7(), tenant_id=tenant_a, company_id=company,
                scope_id=scope.id, price_level_id=uuid.UUID(setup["level"]["id"]),
                valid_from=dt.date(2090, 1, 1), valid_to=None, row_version=1,
            ))
    direct = await resolve(client, root, auth, ids, party_id=str(buyer))
    assert direct["amount"] == "100.0000"
    assert direct["buyer_pricing_chain"] == [{"kind": "party", "ref": str(buyer)}]
    unknown = await client.post(
        root + "/prices/resolve", headers=auth,
        json=query(ids, party_id=str(uuid7())),
    )
    assert unknown.status_code == 422
    assert "membership" in unknown.json()["error"]["message"]
    purchase = await client.post(
        root + "/prices/resolve", headers=auth,
        json=query(ids, purpose="PURCHASE", party_id=str(buyer)),
    )
    assert purchase.status_code == 422
