import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from billing_platform.db import tenant_scope
from billing_platform.db.base import Base
from billing_platform.db.session import create_engine
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from catalog.models.pricing import ItemPrice
from tests.pricing_factories import create, foundation, guard, setup_pricing
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """Use separate connections; in-memory SQLite shares one transaction across requests."""
    value = create_engine("sqlite+aiosqlite:///" + (tmp_path / "pricing.db").as_posix())

    @event.listens_for(value.sync_engine, "connect")
    def foreign_keys(connection: Any, _record: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.close()

    async with value.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield value
    finally:
        await value.dispose()


async def test_concurrent_price_publication_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    payload = {
        "series_id": setup["series"]["id"],
        "numeric_revision_id": setup["numeric"]["id"],
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
    }
    first = await create(client, root, auth, "/price-drafts", payload)
    second = await create(client, root, auth, "/price-drafts", payload)
    body = {**guard(second), "expected_version": 1}
    results = await asyncio.gather(
        *(
            client.post(
                root + "/price-drafts/" + draft["id"] + "/publish",
                headers=command_headers(auth),
                json=body,
            )
            for draft in (first, second)
        )
    )
    assert sorted(result.status_code for result in results) == [201, 409], [r.text for r in results]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPrice.id))) == 1
    # Repeated transport requests share one effect even with independent connections.
    unique = {**payload, "valid_from": "2092-01-01", "valid_to": "2092-12-31"}
    receipt = command_headers(auth)
    copies = await asyncio.gather(
        *(client.post(root + "/price-drafts", headers=receipt, json=unique) for _ in range(2))
    )
    # A concurrent follower may exhaust the bounded in-flight wait. The API then
    # explicitly requires retrying the same key; it must converge to the one effect.
    for index, response in enumerate(copies):
        if response.status_code == 409:
            assert response.json()["error"]["message"] == (
                "request is busy; retry with the same idempotency key"
            )
            copies[index] = await client.post(root + "/price-drafts", headers=receipt, json=unique)
    assert [r.status_code for r in copies] == [201, 201], [r.text for r in copies]
    assert len({r.json()["id"] for r in copies}) == 1
    assert sorted(r.headers["Idempotency-Replayed"] for r in copies) == ["false", "true"]
