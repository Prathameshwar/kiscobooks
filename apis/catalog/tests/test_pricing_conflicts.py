import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CatalogPolicyState, IdempotencyKey, Outbox
from catalog.models.pricing import ItemPriceScope
from tests.pricing_storage_factories import seed_pricing
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_duplicate_price_scope_rolls_back_receipt_audit_and_generation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )

    async def counts() -> tuple[int | None, int | None, int | None, int | None]:
        with tenant_scope(tenant_a):
            async with factory() as db:
                return (
                    await db.scalar(select(func.count(ItemPriceScope.id))),
                    await db.scalar(select(func.count(IdempotencyKey.id))),
                    await db.scalar(select(func.count(Outbox.id))),
                    await db.scalar(select(CatalogPolicyState.generation)),
                )

    before = await counts()
    response = await client.post(
        f"/v1/companies/{company}/price-scopes",
        headers=command_headers(auth),
        json={"item_id": str(ids["item"])},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "conflict"
    assert await counts() == before
