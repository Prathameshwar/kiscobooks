"""Schema-level location facts: tenant isolation, reserved codes and the custody rules.

These hold whatever wrote the row, including a repair script the API never saw.
"""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox
from catalog.models.warehouse_policies import ItemWarehousePolicy
from catalog.models.warehouses import DEFAULT_POINTERS, CompanyWarehouseConfiguration, Warehouse
from catalog.tasks.warehouse_policy import default_pointer
from tests.commercial_factories import reference_data
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import RETIRE, auth


def location(tenant: uuid.UUID, company: uuid.UUID, **changes: Any) -> Warehouse:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "code": "GD1",
        "name": "Godown",
        "kind": "GODOWN",
        "is_system": False,
        "is_active": True,
        "row_version": 1,
        **changes,
    }
    return Warehouse(**values)


async def seed_locations(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """One built-in pair plus its configuration row, written directly."""
    with tenant_scope(tenant):
        async with factory.begin() as db:
            main = location(tenant, company, code="MAIN", name="Main", kind="STORE", is_system=True)
            transit = location(
                tenant,
                company,
                code="TRANSIT",
                name="Internal transit",
                kind="INTERNAL_TRANSIT",
                is_system=True,
            )
            db.add_all([main, transit])
            await db.flush()
            db.add(
                CompanyWarehouseConfiguration(
                    id=uuid7(),
                    tenant_id=tenant,
                    company_id=company,
                    main_warehouse_id=main.id,
                    transit_warehouse_id=transit.id,
                    source_version=2,
                    row_version=1,
                    **dict.fromkeys(DEFAULT_POINTERS, main.id),
                )
            )
            return main.id, transit.id


async def test_location_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        await seed_locations(factory, tenant, company)
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                locations = list(await db.scalars(select(Warehouse)))
                assert len(locations) == 2
                assert {row.tenant_id for row in locations} == {tenant}
                assert {row.company_id for row in locations} == {company}
                configurations = list(await db.scalars(select(CompanyWarehouseConfiguration)))
                assert len(configurations) == 1
                assert configurations[0].tenant_id == tenant
                assert configurations[0].company_id == company


async def test_reserved_codes_kinds_and_addresses_are_schema_facts(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    await reference_data(factory)
    await seed_locations(factory, tenant_a, company)
    for changes in (
        # A reserved code without the system flag, and the system flag without one.
        {"code": "MAIN"},
        {"code": "TRANSIT", "kind": "INTERNAL_TRANSIT"},
        {"code": "GD2", "is_system": True},
        # Transit custody and its reserved code are the same fact in both directions.
        {"code": "GD2", "kind": "INTERNAL_TRANSIT"},
        {"code": "TRANSIT", "kind": "STORE", "is_system": True},
        {"kind": "WAREHOUSE"},
        {"row_version": 0},
        # A state with no country, and a state that belongs to another country.
        {"state_code": "IN-MH"},
        {"country_code": "US", "state_code": "IN-MH"},
        {"country_code": "ZZ"},
        # One code per company, whichever row already holds it.
        {"code": "MAIN", "is_system": True, "kind": "STORE"},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(location(tenant_a, company, **changes))
                await db.flush()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = location(
                tenant_a, company, code="GD2", country_code="IN", state_code="IN-MH", city="Pune"
            )
            db.add(row)
            await db.flush()
            identity = row.id
        async with factory() as db:
            stored = await db.get(Warehouse, identity)
            assert stored is not None and stored.state_code == "IN-MH"


async def test_configuration_is_one_row_per_company_pointing_only_at_its_own_locations(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, other = uuid7(), uuid7()
    main, transit = await seed_locations(factory, tenant_a, company)
    alien, _ = await seed_locations(factory, tenant_a, other)
    valid: dict[str, Any] = {
        "tenant_id": tenant_a,
        "company_id": company,
        "main_warehouse_id": main,
        "transit_warehouse_id": transit,
        "source_version": 2,
        "row_version": 1,
        **dict.fromkeys(DEFAULT_POINTERS, main),
    }
    for changes in (
        # The singleton already exists for this company.
        {},
        {"row_version": 0},
        {"source_version": 0},
        # Custody must be a different location from the built-in store.
        {"main_warehouse_id": transit},
        # Every pointer is a composite (tenant, company, id) reference.
        {"main_warehouse_id": alien},
        {"transit_warehouse_id": alien},
        {"default_sale_warehouse_id": alien},
        {"default_purchase_warehouse_id": alien},
        {"default_customer_return_warehouse_id": alien},
        {"default_opening_warehouse_id": alien},
        {"default_opening_warehouse_id": uuid7()},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(CompanyWarehouseConfiguration(id=uuid7(), **{**valid, **changes}))
                await db.flush()


async def test_default_pointer_detection_is_company_scoped(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, other = uuid7(), uuid7()
    main, transit = await seed_locations(factory, tenant_a, company)
    foreign_main, _ = await seed_locations(factory, tenant_a, other)
    with tenant_scope(tenant_a):
        async with factory() as db:
            configuration = CompanyWarehouseConfiguration
            assert await default_pointer(db, configuration, company, main) is True
            # Custody is never an activity default, so retiring rules never see it that way.
            assert await default_pointer(db, configuration, company, transit) is False
            assert await default_pointer(db, configuration, company, foreign_main) is False
            assert await default_pointer(db, configuration, other, main) is False
            # The product level answers through the same probe, and no product policy exists here.
            assert await default_pointer(db, ItemWarehousePolicy, company, main) is False


async def test_a_location_holding_an_activity_default_cannot_be_retired(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Reachable only once a default points somewhere other than the reserved Main row.

    Phase 3 adds the typed action that repoints it; until then the state is produced here
    directly, because the rule has to hold against the state, not against the route.
    """
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=RETIRE)
    route = f"/v1/companies/{company}/warehouses"
    created = await client.post(
        route,
        headers=command_headers(current),
        json={"code": "GD1", "name": "Godown", "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    identity = uuid.UUID(created.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            configuration = await db.scalar(select(CompanyWarehouseConfiguration))
            assert configuration is not None
            configuration.default_sale_warehouse_id = identity
    refused = await client.post(
        f"{route}/{identity}/deactivate",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["message"].startswith("reassign the company activity default")
    with tenant_scope(tenant_a):
        async with factory() as db:
            stored = await db.get(Warehouse, identity)
            assert stored is not None and stored.is_active is True and stored.row_version == 1


async def test_a_refused_location_write_leaves_no_row_and_no_audit_event(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, features=("inventory",))
    refused = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(current),
        json={"code": "GD1", "name": "Godown", "kind": "GODOWN"},
    )
    assert refused.status_code == 409, refused.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Warehouse.id))) == 0
            assert await db.scalar(select(func.count(CompanyWarehouseConfiguration.id))) == 0
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.aggregate_type.in_(
                            ("catalog.warehouse", "catalog.company_warehouse_configuration")
                        )
                    )
                )
                == 0
            )


async def test_a_successful_location_write_emits_one_audit_event_per_row(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouses"
    receipt = command_headers(current)
    created = await client.post(
        route, headers=receipt, json={"code": "GD1", "name": "Godown", "kind": "GODOWN"}
    )
    assert created.status_code == 201, created.text
    replay = await client.post(
        route, headers=receipt, json={"code": "GD1", "name": "Godown", "kind": "GODOWN"}
    )
    assert replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = [
                (row.aggregate_type, row.event_type)
                for row in await db.scalars(
                    select(Outbox).where(
                        Outbox.tenant_id == tenant_a,
                        Outbox.aggregate_type.like("catalog.%warehouse%"),
                    )
                )
            ]
    # Main, transit and the client's own location, plus the configuration singleton and the
    # one operation policy each of the three locations starts with. A replay adds none of them.
    assert sorted(events) == [
        (
            "catalog.company_warehouse_configuration",
            "catalog.company_warehouse_configuration.create",
        ),
        ("catalog.warehouse", "catalog.warehouse.create"),
        ("catalog.warehouse", "catalog.warehouse.create"),
        ("catalog.warehouse", "catalog.warehouse.create"),
        *(
            (
                "catalog.warehouse_operation_policy_revision",
                "catalog.warehouse_operation_policy_revision.create",
            )
            for _ in range(3)
        ),
    ]
    renamed = await client.patch(
        f"{route}/{created.json()['id']}",
        headers=command_headers(current),
        json={"expected_version": 1, "name": "North godown"},
    )
    assert renamed.status_code == 200, renamed.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            updates = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.tenant_id == tenant_a,
                        Outbox.event_type == "catalog.warehouse.update",
                    )
                )
            )
    assert len(updates) == 1
    # Audit evidence carries references and safe scalars, never the location's label or address.
    assert set(updates[0].payload["changes"]) == {"name"}
    assert updates[0].payload["changes"]["name"] == {"changed": True}
    assert updates[0].payload["actor_user_id"] == str(user)
