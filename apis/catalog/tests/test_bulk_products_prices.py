import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily, UnitOfMeasure
from catalog.models.pricing import ItemPrice
from tests.bulk_factories import post, run
from tests.pricing_factories import foundation, publish_price, setup_pricing
from tests.product_factories import setup_product
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_dependency_version_change_requires_a_new_review(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(
        client,
        root,
        auth,
        "",
        {
            "format": "JSON",
            "records": [
                {
                    "key": "family",
                    "change_set": "product",
                    "resource": "product_family",
                    "data": body,
                }
            ],
        },
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    review = (await client.get(root + "/" + job["id"], headers=auth)).json()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            unit = await db.get(UnitOfMeasure, uuid.UUID(body["default_item"]["base_unit_id"]))
            assert unit is not None
            unit.row_version += 1
            unit.name = "Changed dependency"
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {"expected_version": review["row_version"], "selection_digest": review["selection_digest"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"


async def reviewed_commit(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    auth: dict[str, str],
    body: dict[str, Any],
    *,
    version: int | None = None,
) -> str:
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", body)
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    state = await run(factory, tenant, company, user, job["id"], version=version)
    errors = (await client.get(root + "/" + job["id"] + "/records", headers=auth)).json()
    assert state == "READY", [
        (x["logical_key"], x["state"], x["error_code"], x.get("error_fields"))
        for x in errors["items"]
        if x["error_code"]
    ]
    review = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await post(
        client,
        root,
        auth,
        f"/{job['id']}/commit",
        {"expected_version": review["row_version"], "selection_digest": review["selection_digest"]},
    )
    assert await run(factory, tenant, company, user, job["id"], version=version) == "SUCCEEDED"
    return str(job["id"])


async def test_product_aggregate_uses_native_create_and_staged_sku_target(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "records": [
                {
                    "key": "family",
                    "change_set": "product",
                    "resource": "product_family",
                    "data": body,
                },
                {
                    "key": "sku",
                    "change_set": "product",
                    "resource": "item",
                    "action": "UPDATE",
                    "target": {"record": "family", "field": "default_item.id"},
                    "data": {"name": "Reviewed SKU"},
                },
            ],
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(ProductFamily)))) == 1
            assert (await db.scalars(select(Item.name))).one() == "Reviewed SKU"


async def test_price_adjustment_publishes_exact_future_revision_with_rounding(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    setup = await foundation(client, root, auth, ids)
    _, published = await publish_price(client, root, auth, setup, amount="123.4567")
    job = await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        auth,
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "price",
                    "change_set": "sku",
                    "resource": "item_price",
                    "action": "ADJUST",
                    "target": {"id": published["id"]},
                    "data": {
                        "method": "PERCENT",
                        "value": "2.5",
                        "rounding_mode": "HALF_UP",
                        "currency": "INR",
                        "unit_revision_id": str(ids["item_unit_revision"]),
                        "price_level_id": setup["level"]["id"],
                        "price_basis_quantity": "1",
                        "numeric_revision_id": setup["numeric"]["id"],
                        "valid_from": "2091-01-01",
                    },
                }
            ],
        },
    )
    records = (await client.get(root + "/bulk-jobs/" + job + "/records", headers=auth)).json()[
        "items"
    ]
    preview = await client.get(
        root + "/bulk-jobs/" + job + "/records/" + records[0]["id"], headers=auth
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["before"]["amount"] == "123.4567"
    assert preview.json()["after"]["amount"] == "126.5431"
    assert preview.json()["result"]["id"] != published["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            rows = list(await db.scalars(select(ItemPrice).order_by(ItemPrice.valid_from)))
            assert len(rows) == 2 and str(rows[0].valid_to) == "2090-12-31"


async def test_bulk_review_combines_configuration_pricing_tax_and_activation(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datetime as dt

    from catalog.models.tax import ItemActivation
    from catalog.tasks import activation
    from tests.tax_factories import DATE, seed_tax

    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    job_id = await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        auth,
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": action.lower(),
                    "change_set": "product",
                    "resource": "item",
                    "action": action,
                    "target": {"id": str(ids["item"])},
                    "data": {"as_of": str(DATE)},
                }
                for action in ("ADOPT_CONFIGURATION", "ACTIVATE")
            ],
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None and item.status == "ACTIVE"
            assert len(list(await db.scalars(select(ItemActivation.id)))) == 1
    rows = (await client.get(root + "/bulk-jobs/" + job_id + "/records", headers=auth)).json()[
        "items"
    ]
    assert len(rows) == 2 and all(row["state"] == "APPLIED" for row in rows)


@pytest.mark.parametrize(
    "method,expected", [("DELTA", ["101.2500", "81.2500"]), ("SET", ["1.2500", "1.2500"])]
)
async def test_tier_adjustments_preserve_boundaries_and_exact_values(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    method: str,
    expected: list[str],
) -> None:
    from catalog.models.pricing import ItemPriceTier

    root, auth, ids = await setup_pricing(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    configured = await foundation(client, root, auth, ids)
    _, original = await publish_price(
        client,
        root,
        auth,
        configured,
        price_method="TIERS",
        amount=None,
        tiers=[
            {"min_quantity": "0", "max_quantity": "10", "amount": "100"},
            {"min_quantity": "10", "amount": "80"},
        ],
    )
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        auth,
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "price",
                    "change_set": "sku",
                    "resource": "item_price",
                    "action": "ADJUST",
                    "target": {"id": original["id"]},
                    "data": {
                        "method": method,
                        "value": "1.25",
                        "rounding_mode": "HALF_UP",
                        "currency": "INR",
                        "unit_revision_id": str(ids["item_unit_revision"]),
                        "price_level_id": configured["level"]["id"],
                        "price_basis_quantity": "1",
                        "numeric_revision_id": configured["numeric"]["id"],
                        "valid_from": "2091-01-01",
                        "valid_to": "2091-12-31",
                    },
                }
            ],
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            current = (
                await db.scalars(
                    select(ItemPrice).where(ItemPrice.supersedes_id == uuid.UUID(original["id"]))
                )
            ).one()
            tiers = list(
                await db.scalars(
                    select(ItemPriceTier)
                    .where(ItemPriceTier.price_id == current.id)
                    .order_by(ItemPriceTier.min_quantity)
                )
            )
            assert [str(tier.amount) for tier in tiers] == expected
            assert [str(tier.min_quantity) for tier in tiers] == ["0.0000", "10.0000"]
