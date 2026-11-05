from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from catalog.models import CatalogPolicyState, Outbox
from catalog.models.commercial import Brand, BrandManufacturer, ProductTypeRevision
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.commercial_history import PRODUCTION, REVISION, command
from tests.commercial_factories import auth, reference_data, seed_commercial
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers


async def test_revision_and_policy_counters_do_not_overflow(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    product_type = (
        await create(
            client, company, current, "product-types", {"code": "T", "name": "Type", "kind": "BOTH"}
        )
    ).json()
    master = f"/v1/companies/{company}/product-types/{product_type['id']}"
    changed = await client.patch(
        master, headers=command_headers(current), json={"expected_version": 1, "kind": "GOODS"}
    )
    assert changed.status_code == 200 and changed.json()["kind"] == "GOODS"
    route = master + "/revisions"
    body = {"inventory_modes": ["STOCK"], "tracking_modes": ["NONE"], "unit_dimensions": ["COUNT"]}
    first = (await client.post(route, headers=command_headers(current), json=body)).json()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, uuid.UUID(first["id"]))
            assert revision is not None
            revision.revision = 2**31 - 1
    exhausted = await client.post(route, headers=command_headers(current), json=body)
    assert exhausted.status_code == 409 and "exhausted" in exhausted.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, uuid.UUID(first["id"]))
            assert revision is not None
            revision.revision = 1
            state = await db.scalar(
                select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
            )
            assert state is not None
            state.generation = 2**63 - 1
    exhausted = await client.post(route, headers=command_headers(current), json=body)
    assert exhausted.status_code == 409 and "exhausted" in exhausted.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductTypeRevision.id))) == 1


async def test_brand_graph_work_is_bounded(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add_all(
                [
                    Brand(tenant_id=tenant_a, company_id=company, code=f"B{index}", name="Brand")
                    for index in range(10001)
                ]
            )
    rejected = await create(
        client, company, current, "brands", {"code": "OVER", "name": "Over capacity"}
    )
    assert rejected.status_code == 409 and "bounds" in rejected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Brand.id))) == 10001
            assert await db.scalar(select(func.count(Outbox.id))) == 0


async def test_database_rejection_rolls_back_commercial_history(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    brand = (
        await create(client, company, current, "brands", {"code": "B", "name": "Brand"})
    ).json()
    maker = (
        await create(client, company, current, "manufacturers", {"code": "M", "name": "Maker"})
    ).json()

    def invalid_version(db: Session, flush_context: Any, instances: Any) -> None:
        # Fault injection into the ORM object; the real database CHECK still rejects it.
        for row in db.new:
            if isinstance(row, BrandManufacturer):
                row.row_version = 0

    event.listen(Session, "before_flush", invalid_version)
    try:
        result = await create(
            client,
            company,
            current,
            "brand-manufacturers",
            {
                "brand_id": brand["id"],
                "manufacturer_id": maker["id"],
                "production_role": "OEM",
                "valid_from": "2020-01-01",
            },
        )
    finally:
        event.remove(Session, "before_flush", invalid_version)
    assert result.status_code == 409, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(BrandManufacturer.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == 2


@pytest.mark.parametrize("production", [True, False])
async def test_history_command_boundary_rejects_wrong_lifecycle_action(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, production: bool
) -> None:
    await reference_data(factory)
    company, user = uuid7(), uuid7()
    await auth(factory, tenant_a, company, user)
    ids = await seed_commercial(factory, tenant_a, company)
    actor = Actor(
        tenant_a,
        user,
        grants=(
            Grant(
                permissions=frozenset(
                    {
                        "brand_manufacturer.read",
                        "brand_manufacturer.manage",
                        "product_type.read",
                        "product_type.manage",
                    }
                ),
                scope=Scope("company", company),
                valid_from=dt.date(2020, 1, 1),
            ),
        ),
    )
    with tenant_scope(tenant_a), pytest.raises(ValidationFailedError):
        await command(
            factory,
            actor,
            company,
            PRODUCTION if production else REVISION,
            key=str(uuid7()),
            body=ExpectedVersion(expected_version=1),
            action="update" if production else "close",
            object_id=ids["brand_manufacturer" if production else "product_type_revision"],
            parent_id=None if production else ids["product_type"],
        )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == 0
            assert (
                await db.scalar(
                    select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
                )
                is None
            )
