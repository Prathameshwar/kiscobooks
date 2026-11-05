import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.pricing import ItemPrice
from catalog.tasks import bulk_prices
from catalog.tasks.bulk_prices import PriceAdjustment
from catalog.tasks.bulk_registry import Runtime
from catalog.tasks.pricing_publication import draft_input
from tests.conftest import ACTOR_SECRET
from tests.pricing_factories import foundation, guard, publish_price, setup_pricing
from tests.test_bulk_matching import actor
from tests.test_bulk_products_prices import reviewed_commit

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("purpose", ["SALE", "PURCHASE"])
async def test_filtered_price_adjustment_preserves_scope_and_checks_explicit_context(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    purpose: str,
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    prepared = await foundation(client, root, auth, ids, purpose=purpose)
    _, published = await publish_price(client, root, auth, prepared)
    data = {
        "method": "SET",
        "value": "90.0000",
        "rounding_mode": "DOWN",
        "currency": "INR",
        "unit_revision_id": str(ids["item_unit_revision"]),
        "price_level_id": prepared["level"]["id"] if purpose == "SALE" else None,
        "price_basis_quantity": "1",
        "numeric_revision_id": prepared["numeric"]["id"],
        "valid_from": "2091-01-01",
        "valid_to": "2091-12-31",
    }
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            runtime = Runtime(
                db,
                factory,
                actor(tenant_a, company, ids["actor_user"]),
                company,
                ACTOR_SECRET.encode(),
            )
            body = PriceAdjustment.model_validate(
                {**data, **guard(published), "expected_version": published["row_version"]}
            )
            with pytest.raises(ConflictError, match="source changed"):
                await bulk_prices.adjust(
                    runtime,
                    body.model_copy(update={"expected_version": 99}),
                    uuid.UUID(published["id"]),
                    "stale",
                )
            with pytest.raises(ValidationFailedError, match="explicitly selected"):
                await bulk_prices.adjust(
                    runtime,
                    body.model_copy(update={"currency": "USD"}),
                    uuid.UUID(published["id"]),
                    "currency",
                )
            original = draft_input

            async def formula(*args: Any, **kwargs: Any) -> Any:
                return (await original(*args, **kwargs)).model_copy(
                    update={"price_method": "FORMULA"}
                )

            with monkeypatch.context() as patch:
                patch.setattr(bulk_prices, "draft_input", formula)
                with pytest.raises(ValidationFailedError, match="explicit native draft"):
                    await bulk_prices.adjust(runtime, body, uuid.UUID(published["id"]), "recipe")
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        auth,
        {
            "format": "FILTER",
            "resource": "item_price",
            "action": "ADJUST",
            "filters": {"series_id": prepared["series"]["id"]},
            "data": data,
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            prices = list(await db.scalars(select(ItemPrice).order_by(ItemPrice.valid_from)))
            assert len(prices) == 2 and str(prices[1].amount) == "90.0000"
            assert str(prices[1].valid_to) == "2091-12-31"


async def test_price_selection_cannot_filter_on_a_protected_plan_purpose(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from billing_platform.ids import uuid7

    from tests.test_unit_api import policy, seed_context

    root, auth, ids = await setup_pricing(factory, tenant_a)
    prepared = await foundation(client, root, auth, ids)
    await publish_price(client, root, auth, prepared)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await seed_context(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        (policy(ids["actor_user"], "purpose", "read", entity="catalog.price_plan"),),
        version=3,
    )
    response = await client.post(
        root + "/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "format": "FILTER",
            "resource": "item_price",
            "action": "ADJUST",
            "all_rows": True,
            "data": {"method": "SET", "value": "1"},
        },
    )
    assert response.status_code == 403, response.text
