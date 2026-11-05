"""Provisioning under real concurrency: one built-in set per company, whoever races."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from billing_platform.db import tenant_scope
from billing_platform.db.base import Base
from billing_platform.db.session import create_engine
from billing_platform.ids import uuid7
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from catalog.models.warehouses import CompanyWarehouseConfiguration, Warehouse
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import auth


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """Use separate connections; in-memory SQLite shares one transaction across requests."""
    value = create_engine("sqlite+aiosqlite:///" + (tmp_path / "warehouse.db").as_posix())

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


async def _built_in_set(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[int, int]:
    with tenant_scope(tenant):
        async with factory() as db:
            return (
                await db.scalar(select(func.count(Warehouse.id))) or 0,
                await db.scalar(select(func.count(CompanyWarehouseConfiguration.id))) or 0,
            )


async def test_concurrent_bootstrap_provisions_exactly_one_built_in_set(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """The company policy lock serializes provisioning; the reserved code is the backstop."""
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouse-configuration/bootstrap"
    results = await asyncio.gather(
        *(client.post(route, headers=command_headers(current), json={}) for _ in range(4))
    )
    accepted = [response for response in results if response.status_code == 201]
    assert accepted, [response.text for response in results]
    assert len({response.json()["id"] for response in accepted}) == 1
    assert await _built_in_set(factory, tenant_a) == (2, 1)


async def test_concurrent_first_locations_share_one_provisioned_set(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Two clients create their first godown at once; catch-up provisioning runs once."""
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouses"
    results = await asyncio.gather(
        *(
            client.post(
                route,
                headers=command_headers(current),
                json={"code": code, "name": code.title(), "kind": "GODOWN"},
            )
            for code in ("GD1", "GD2", "GD3")
        )
    )
    accepted = [response for response in results if response.status_code == 201]
    assert accepted, [response.text for response in results]
    warehouses, configurations = await _built_in_set(factory, tenant_a)
    assert configurations == 1
    assert warehouses == 2 + len(accepted)


async def test_bootstrap_replay_under_concurrency_has_one_effect(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouse-configuration/bootstrap"
    receipt = command_headers(current)
    results = await asyncio.gather(
        *(client.post(route, headers=receipt, json={}) for _ in range(3))
    )
    # A follower may exhaust the bounded in-flight wait; no follower may double-provision.
    assert {response.status_code for response in results} <= {201, 409, 503}
    assert any(response.status_code == 201 for response in results), [
        response.text for response in results
    ]
    assert await _built_in_set(factory, tenant_a) == (2, 1)
