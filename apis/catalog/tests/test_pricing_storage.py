import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.pricing import (
    PRICING_MODELS,
    PriceLevelAssignment,
    PriceLevelAssignmentScope,
)
from catalog.models.projections import CustomerPricingProjection
from tests.pricing_storage_factories import seed_pricing
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
PATHS = (
    "price-levels",
    "price-plans",
    "company-pricing-policies",
    "price-scopes",
    "price-numeric-revisions",
    "price-series",
    "price-drafts",
    "prices",
    "price-tiers",
    "purchase-price-terms",
    "reference-costs",
    "product-mrps",
    "price-formulas",
    "commercial-policy-scopes",
    "commercial-guard-rules",
    "discount-ceilings",
    "item-commercial-policies",
)
# Assignment authoring and its list/detail routes are deferred to v1.1
# (docs/catalog-v1-completion-plan.md, Phase 3 "Deferred to v1.1"). In v1 these
# tables are read only through ``/customer-pricing/effective``, which is checked
# for permission, company scope and input below instead of per-table routes.
EFFECTIVE_READ_ONLY = (PriceLevelAssignmentScope, PriceLevelAssignment)
ROUTED_MODELS = tuple(model for model in PRICING_MODELS if model not in EFFECTIVE_READ_ONLY)


async def test_all_pricing_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    _, a = await seed_pricing(factory, tenant_a)
    _, b = await seed_pricing(factory, tenant_b)
    for tenant, own, foreign in ((tenant_a, a, b), (tenant_b, b, a)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in PRICING_MODELS:
                    ids = set(await db.scalars(select(model.id)))
                    assert own[model.__tablename__] in ids
                    assert foreign[model.__tablename__] not in ids


async def test_every_pricing_read_checks_company_permission_and_input(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, a = await seed_pricing(factory, tenant_a)
    other, b = await seed_pricing(factory, tenant_a)
    default_buyer = uuid7()
    # Positive customer reads need verified company-owned membership facts.
    # A known empty type is distinct from a buyer missing from this company's source.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for buyer in (a["customer_party"], default_buyer):
                db.add(
                    CustomerPricingProjection(
                        id=uuid7(),
                        tenant_id=tenant_a,
                        company_id=company,
                        source_id=uuid7(),
                        source_version=1,
                        party_id=buyer,
                        customer_type_code=None,
                        valid_from=dt.date(2090, 1, 1),
                        valid_to=None,
                        is_active=True,
                    )
                )
    root = f"/v1/companies/{company}"
    auth = headers(
        company, tenant=tenant_a, user=a["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    no_permission = headers(
        company, tenant=tenant_a, user=a["actor_user"], permission=["catalog.readiness.read"]
    )
    assert set(PRICING_MODELS) == set(ROUTED_MODELS) | set(EFFECTIVE_READ_ONLY)
    for model, path in zip(ROUTED_MODELS, PATHS, strict=True):
        url = root + "/" + path
        detail = await client.get(url + "/" + str(a[model.__tablename__]), headers=auth)
        assert detail.status_code == 200, (path, detail.text)
        page = await client.get(url, headers=auth, params={"limit": 1})
        assert page.status_code == 200, (path, page.text)
        assert "source_reference" not in page.json()["items"][0]
        assert (await client.get(url, headers=no_permission)).status_code == 403, path
        assert (await client.get(url)).status_code == 401, path
        assert (
            await client.get(url, headers=auth, params={"made_up": "x"})
        ).status_code == 422, path
        foreign = await client.get(url + "/" + str(b[model.__tablename__]), headers=auth)
        assert foreign.status_code == 403, (path, foreign.text)
        wrong = await client.get(f"/v1/companies/{other}/" + path, headers=auth)
        assert wrong.status_code == 403, (path, wrong.text)

    effective = root + "/customer-pricing/effective"
    params = {"party_id": str(a["customer_party"]), "as_of": "2090-06-01"}
    own = await client.get(effective, headers=auth, params=params)
    assert own.status_code == 200, own.text
    assert own.json()["chain"] == [{"kind": "party", "ref": str(a["customer_party"])}]
    assert own.json()["price_level_id"] == str(a["price_level"])
    known_default = await client.get(
        effective,
        headers=auth,
        params={"party_id": str(default_buyer), "as_of": "2090-06-01"},
    )
    assert known_default.status_code == 200, known_default.text
    assert known_default.json()["chain"] == [{"kind": "company", "ref": "default"}]
    assert known_default.json()["price_level_id"] == str(a["price_level"])
    # The other company's assignment for its own party never resolves here.
    leaked = await client.get(
        effective,
        headers=auth,
        params={"party_id": str(b["customer_party"]), "as_of": "2090-06-01"},
    )
    assert leaked.status_code == 422, leaked.text
    assert "membership is missing or inactive" in leaked.json()["error"]["message"]
    assert (await client.get(effective, headers=no_permission, params=params)).status_code == 403
    assert (await client.get(effective, params=params)).status_code == 401
    bad = {**params, "made_up": "x"}
    assert (await client.get(effective, headers=auth, params=bad)).status_code == 422
    wrong_company = f"/v1/companies/{other}/customer-pricing/effective"
    assert (await client.get(wrong_company, headers=auth, params=params)).status_code == 403


async def test_tier_currency_is_bound_to_its_published_price(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from decimal import Decimal

    from sqlalchemy.exc import IntegrityError

    from catalog.models.pricing import ItemPriceTier

    company, ids = await seed_pricing(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db:
            original = await db.get(ItemPriceTier, ids["item_price_tier"])
            assert original is not None and isinstance(original.amount, Decimal)
        with pytest.raises(IntegrityError, match="(?i)foreign key"):
            async with factory.begin() as db:
                db.add(
                    ItemPriceTier(
                        tenant_id=tenant_a,
                        company_id=company,
                        price_id=ids["item_price"],
                        draft_id=None,
                        min_quantity=Decimal(10),
                        max_quantity=None,
                        amount=Decimal(90),
                        currency="USD",
                    )
                )
                await db.flush()
