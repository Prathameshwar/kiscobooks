"""Native 2,000-SKU/4,000-price fixture and dated lean-page measurement."""

import datetime as dt
import uuid
from time import perf_counter

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ItemUnitBinding, ItemUnitRevision
from catalog.models import pricing as m
from tests.test_api import headers
from tests.test_classification_api import setup_source


async def benchmark(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
) -> dict[str, object]:
    common = {"tenant_id": tenant, "company_id": company}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            items = list(await db.scalars(select(Item).where(Item.company_id == company)))
            assert len(items) == 2000
            level = m.PriceLevel(code="PRICE1", name="Retail", ordinal=1, is_active=True, **common)
            db.add(level)
            await db.flush()
            plan = m.PricePlan(
                code="SALE",
                name="Retail",
                purpose="SALE",
                price_level_id=level.id,
                currency="INR",
                tax_basis="EXCLUSIVE",
                **common,
            )
            db.add(plan)
            await db.flush()
            bindings = [
                ItemUnitBinding(
                    id=uuid7(),
                    item_id=item.id,
                    code="BASE",
                    usage_role="BASE",
                    unit_id=item.base_unit_id,
                    **common,
                )
                for item in items
            ]
            db.add_all(bindings)
            await db.flush()
            revisions = [
                ItemUnitRevision(
                    id=uuid7(),
                    binding_id=binding.id,
                    revision=1,
                    valid_from=dt.date(2090, 1, 1),
                    conversion_mode="FIXED",
                    numerator=1,
                    denominator=1,
                    quantity_decimal_places=0,
                    quantity_increment="1",
                    fractional_entry=False,
                    **common,
                )
                for binding in bindings
            ]
            db.add_all(revisions)
            await db.flush()
            scopes = [
                m.ItemPriceScope(id=uuid7(), item_id=item.id, subject_kind="SKU", **common)
                for item in items
            ]
            numbers = [
                m.ItemPriceNumericRevision(
                    id=uuid7(),
                    item_id=item.id,
                    unit_revision_id=revision.id,
                    currency="INR",
                    price_decimal_places=4,
                    valid_from=dt.date(2090, 1, 1),
                    **common,
                )
                for item, revision in zip(items, revisions, strict=True)
            ]
            db.add_all([*scopes, *numbers])
            await db.flush()
            series = [
                m.ItemPriceSeries(
                    id=uuid7(),
                    item_id=item.id,
                    price_scope_id=scope.id,
                    plan_id=plan.id,
                    unit_revision_id=revision.id,
                    currency="INR",
                    audience_kind="STANDARD",
                    **common,
                )
                for item, scope, revision in zip(items, scopes, revisions, strict=True)
            ]
            db.add_all(series)
            await db.flush()
            predecessors: dict[uuid.UUID, uuid.UUID] = {}
            for year, amount in ((2090, "100"), (2091, "110")):
                drafts = [
                    m.ItemPriceDraft(
                        id=uuid7(),
                        item_id=item.id,
                        series_id=price_series.id,
                        unit_revision_id=revision.id,
                        numeric_revision_id=number.id,
                        currency="INR",
                        status="PUBLISHED",
                        price_method="FIXED",
                        amount=amount,
                        price_basis_quantity="1",
                        source_reference="Benchmark definition",
                        valid_from=dt.date(year, 1, 1),
                        valid_to=dt.date(2090, 12, 31) if year == 2090 else None,
                        **common,
                    )
                    for item, price_series, revision, number in zip(
                        items, series, revisions, numbers, strict=True
                    )
                ]
                db.add_all(drafts)
                await db.flush()
                prices = [
                    m.ItemPrice(
                        id=uuid7(),
                        source_draft_id=draft.id,
                        supersedes_id=predecessors.get(draft.series_id),
                        **{
                            field: getattr(draft, field)
                            for field in (
                                "item_id",
                                "series_id",
                                "unit_revision_id",
                                "numeric_revision_id",
                                "currency",
                                "price_method",
                                "amount",
                                "price_basis_quantity",
                                "source_reference",
                                "valid_from",
                                "valid_to",
                            )
                        },
                        **common,
                    )
                    for draft in drafts
                ]
                db.add_all(prices)
                await db.flush()
                predecessors = {price.series_id: price.id for price in prices}
    # Refresh real signed facts after fixture loading; never relax production source TTL.
    await setup_source(factory, tenant, company, user, version=3)
    auth = headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS))
    seen: set[str] = set()
    timings: list[float] = []
    cursor: str | None = None
    for _ in range(10):
        params = {"limit": "200", "as_of": "2091-01-01"}
        if cursor is not None:
            params["cursor"] = cursor
        start = perf_counter()
        page = await client.get(f"/v1/companies/{company}/prices", headers=auth, params=params)
        timings.append(round((perf_counter() - start) * 1000, 3))
        assert page.status_code == 200, page.text
        rows = page.json()["items"]
        assert len(rows) == 200
        assert all(row["amount"] == "110.0000" and "source_reference" not in row for row in rows)
        current = {row["id"] for row in rows}
        assert not seen & current
        seen |= current
        cursor = page.json()["page"]["next_cursor"]
    assert len(seen) == 2000 and cursor is None
    return {"skus": 2000, "dated_price_rows": 4000, "pages": 10, "page_ms": timings}
