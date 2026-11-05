import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.units import UnitOfMeasure
from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.source_factories import all_facts
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_pricing_resolution import query, resolve

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def feature(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    version: int = 3,
    enabled: bool = True,
) -> None:
    record = SnapshotRecord(
        kind="feature",
        id=uuid7(),
        data={
            "company_id": str(company),
            "feature_key": "multi_price_levels",
            "is_enabled": enabled,
            "locked_at": None,
        },
    )
    await setup_source(
        factory, tenant, company, user, version=version, facts=(*all_facts(company, user), record)
    )


async def box(
    client: httpx.AsyncClient,
    root: str,
    auth: dict[str, str],
    ids: dict[str, uuid.UUID],
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
) -> tuple[uuid.UUID, dict[str, Any]]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            master = UnitOfMeasure(
                tenant_id=tenant,
                company_id=uuid.UUID(root.rsplit("/", 1)[1]),
                code="BOX",
                symbol="box",
                name="Box",
                dimension="COUNT",
                decimal_places=0,
                quantity_increment=Decimal(1),
            )
            db.add(master)
            await db.flush()
            unit_id = str(master.id)
    result = await client.post(
        root + f"/items/{ids['item']}/unit-bindings",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "code": "BOX",
            "unit_id": unit_id,
            "role": "PACK",
            "numerator": 12,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "valid_from": "2090-01-01",
        },
    )
    assert result.status_code == 200, result.text
    with tenant_scope(tenant):
        async with factory() as db:
            revision = await db.scalar(
                select(ItemUnitRevision)
                .join(ItemUnitBinding, ItemUnitRevision.binding_id == ItemUnitBinding.id)
                .where(ItemUnitBinding.item_id == ids["item"], ItemUnitBinding.code == "BOX")
            )
            assert revision is not None
            return revision.id, {**result.json(), "source_version": 2}


async def test_explicit_box_price_beats_permitted_exact_base_derivation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    await publish_price(client, root, auth, setup, amount="80")
    revision, token = await box(client, root, auth, ids, factory, tenant_a)
    assert (
        await client.post(
            root + "/prices/resolve", headers=auth, json=query(ids, unit_revision_id=str(revision))
        )
    ).status_code == 409
    policy = await create(
        client,
        root,
        auth,
        "/company-pricing-policies",
        {
            **guard(token),
            "default_level_id": setup["level"]["id"],
            "valid_from": "2091-01-01",
            "supersedes_id": setup["policy"]["id"],
            "expected_previous_version": 1,
            "sale_unit_mode": "EXACT_BASE_DERIVATION",
        },
    )
    derived = await resolve(
        client, root, auth, ids, as_of="2091-01-01", unit_revision_id=str(revision)
    )
    assert derived["unit_derivation_used"] is True and derived["exact_consideration"] == {
        "numerator": "960",
        "denominator": "1",
    }
    precision = await create(
        client,
        root,
        auth,
        "/price-numeric-revisions",
        {
            **guard(policy),
            "item_id": str(ids["item"]),
            "unit_revision_id": str(revision),
            "currency": "INR",
            "price_decimal_places": 2,
            "valid_from": "2091-01-01",
        },
    )
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": setup["plan"]["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(revision),
        },
    )
    await publish_price(
        client,
        root,
        auth,
        {**setup, "series": series, "numeric": precision},
        amount="900",
        valid_from="2091-01-01",
    )
    explicit = await resolve(
        client, root, auth, ids, as_of="2091-01-01", unit_revision_id=str(revision)
    )
    assert explicit["unit_derivation_used"] is False and explicit["amount"] == "900.0000"
    assert (await resolve(client, root, auth, ids, as_of="2091-01-01"))["amount"] == "80.0000"


async def test_multiple_levels_explicit_fallback_and_administrative_selection(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await feature(factory, tenant_a, company, ids["actor_user"])
    setup = await foundation(client, root, auth, ids)
    levels = (await client.get(root + "/price-levels", headers=auth)).json()["items"]
    assert [r["code"] for r in levels] == ["PRICE1", "PRICE2", "PRICE3"]
    additional = await create(
        client, root, auth, "/price-levels", {"code": "EXPORT", "name": "Export", "ordinal": 4}
    )
    no_change = await create(client, root, auth, "/pricing/bootstrap", {})
    assert no_change["policy_generation"] == additional["policy_generation"]
    alternate = await create(
        client,
        root,
        auth,
        "/price-plans",
        {
            "code": "WHOLESALE",
            "name": "Wholesale",
            "purpose": "SALE",
            "price_level_id": levels[1]["id"],
            "currency": "INR",
            "tax_basis": "EXCLUSIVE",
        },
    )
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": alternate["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    _, price = await publish_price(client, root, auth, {**setup, "series": series}, amount="90")
    await create(
        client,
        root,
        auth,
        "/company-pricing-policies",
        {
            **guard(price),
            "default_level_id": setup["level"]["id"],
            "missing_price_policy": "FALLBACK",
            "fallback_level_id": levels[1]["id"],
            "valid_from": "2091-01-01",
            "supersedes_id": setup["policy"]["id"],
            "expected_previous_version": 1,
        },
    )
    result = await resolve(client, root, auth, ids, as_of="2091-01-01")
    assert result["amount"] == "90.0000" and result["fallback_used"] is True
    override = await resolve(
        client,
        root,
        auth,
        ids,
        price_level_id=levels[1]["id"],
        override_reason="Approved administrative preview",
    )
    assert override["amount"] == "90.0000" and override["fallback_used"] is False
    assert (
        await client.post(
            root + "/prices/resolve", headers=auth, json=query(ids, price_level_id=levels[1]["id"])
        )
    ).status_code == 422
    await feature(factory, tenant_a, company, ids["actor_user"], version=4, enabled=False)
    assert (
        await client.post(
            root + "/prices/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
        )
    ).status_code == 409
    assert len((await client.get(root + "/price-levels", headers=auth)).json()["items"]) == 4


async def test_fallback_level_uses_the_same_explicit_unit_derivation_policy(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await feature(factory, tenant_a, company, ids["actor_user"])
    setup = await foundation(client, root, auth, ids)
    levels = (await client.get(root + "/price-levels", headers=auth)).json()["items"]
    plan = await create(
        client,
        root,
        auth,
        "/price-plans",
        {
            "code": "FALLBACK",
            "name": "Fallback",
            "purpose": "SALE",
            "price_level_id": levels[1]["id"],
            "currency": "INR",
            "tax_basis": "EXCLUSIVE",
        },
    )
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": plan["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    await publish_price(client, root, auth, {**setup, "series": series}, amount="90")
    revision, token = await box(client, root, auth, ids, factory, tenant_a)
    token["source_version"] = 3
    await create(
        client,
        root,
        auth,
        "/company-pricing-policies",
        {
            **guard(token),
            "default_level_id": setup["level"]["id"],
            "missing_price_policy": "FALLBACK",
            "fallback_level_id": levels[1]["id"],
            "sale_unit_mode": "EXACT_BASE_DERIVATION",
            "valid_from": "2091-01-01",
            "supersedes_id": setup["policy"]["id"],
            "expected_previous_version": 1,
        },
    )
    result = await resolve(
        client, root, auth, ids, as_of="2091-01-01", unit_revision_id=str(revision)
    )
    assert result["fallback_used"] is True and result["unit_derivation_used"] is True
    assert result["exact_consideration"] == {"numerator": "1080", "denominator": "1"}
