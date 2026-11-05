"""Location grouping, dated membership and bins over HTTP.

docs/catalog-warehouses.md §3 and §4. Four claims carry the weight here, and each is
asserted as a refusal or as a *past* answer rather than as a convenience:

* a group is a reporting dimension, never a place — nothing can be stored in one, no
  document may select one, and being in one grants no access to its member locations;
* the hierarchy is dated, so "which locations were under this group in March" keeps
  answering what it answered in March, across every later reparenting;
* a location has one primary group on any date, so no rollup double-counts it;
* a bin belongs to one location for life, and its code is unique only within that one.

Schema-level facts that must hold whoever wrote the row — tenant isolation and the
membership start key — are asserted here too, by writing rows directly.
"""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouses import WarehouseBin
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_warehouse_storage import seed_locations
from tests.warehouse_factories import auth, retire

#: Grouping, membership and bins are four permissions, not one: the rollup, the move, the
#: subdivision and the location itself are separately grantable (§3).
GROUPING = (
    "warehouse.read",
    "warehouse.manage",
    "warehouse.publish",
    "warehouse.deactivate",
    "catalog.release.read",
    "warehouse_group.read",
    "warehouse_group.manage",
    "warehouse_group.move",
    "warehouse_bin.read",
    "warehouse_bin.manage",
)
#: The hierarchy starts long before any of these tests run; every *append* is in the future.
PAST = "2020-01-01"
DETAIL_KEYS = {
    "id",
    "code",
    "name",
    "is_active",
    "row_version",
    "company_id",
    "created_at",
    "updated_at",
    "policy_generation",
}


def dated(days: int) -> str:
    """A future business date. Appending an interval in the past is refused, by design."""
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def denial(
    company: uuid.UUID, user: uuid.UUID, entity: str, field: str, access: str
) -> SnapshotRecord:
    """One Identity field policy denying this user a field, tenant-wide."""
    source = next(row for row in all_facts(company, user) if row.kind == "field_policy")
    return SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": entity,
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": field,
            "access": access,
            "condition": None,
        },
    )


async def create_group(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    code: str,
    parent: str | None = None,
    *,
    start: str = PAST,
) -> dict[str, Any]:
    response = await client.post(
        f"/v1/companies/{company}/warehouse-groups",
        headers=command_headers(current),
        json={"code": code, "name": code.title(), "parent_group_id": parent, "valid_from": start},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def create_location(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    code: str,
    kind: str = "GODOWN",
) -> str:
    response = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(current),
        json={"code": code, "name": code.title(), "kind": kind},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def detail(
    client: httpx.AsyncClient, company: uuid.UUID, current: dict[str, str], path: str
) -> dict[str, Any]:
    response = await client.get(f"/v1/companies/{company}{path}", headers=current)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def reparent(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    group: str,
    parent: str | None,
    start: str,
    *,
    version: int | None = None,
    generation: int | None = None,
) -> httpx.Response:
    view = await detail(client, company, current, f"/warehouse-groups/{group}")
    return await client.post(
        f"/v1/companies/{company}/warehouse-groups/{group}/reparent",
        headers=command_headers(current),
        json={
            "expected_version": version if version is not None else view["row_version"],
            "expected_generation": (
                generation if generation is not None else view["policy_generation"]
            ),
            "parent_group_id": parent,
            "effective_from": start,
        },
    )


async def assign(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    location: str,
    group: str | None,
    start: str,
    *,
    version: int | None = None,
    generation: int | None = None,
    reader: dict[str, str] | None = None,
) -> httpx.Response:
    """``reader`` reads the expectations when the acting headers may not read the location."""
    if version is None or generation is None:
        view = await detail(client, company, reader or current, f"/warehouses/{location}")
        version = version if version is not None else view["row_version"]
        generation = generation if generation is not None else view["policy_generation"]
    return await client.put(
        f"/v1/companies/{company}/warehouses/{location}/primary-group",
        headers=command_headers(current),
        json={
            "expected_version": version,
            "expected_generation": generation,
            "group_id": group,
            "effective_from": start,
        },
    )


async def members(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    group: str,
    valid_at: str,
) -> list[str]:
    response = await client.get(
        f"/v1/companies/{company}/warehouse-groups/{group}/members",
        headers=current,
        params={"valid_at": valid_at},
    )
    assert response.status_code == 200, response.text
    return [row["code"] for row in response.json()["items"]]


async def children(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    group: str,
    valid_at: str,
) -> list[str]:
    response = await client.get(
        f"/v1/companies/{company}/warehouse-groups/{group}/children",
        headers=current,
        params={"valid_at": valid_at},
    )
    assert response.status_code == 200, response.text
    return [row["code"] for row in response.json()["items"]]


async def test_group_hierarchy_rejects_cycles_and_excess_depth(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    north = await create_group(client, company, current, "NORTH")
    west = await create_group(client, company, current, "WEST", north["id"])
    before = await detail(client, company, current, f"/warehouse-groups/{north['id']}")
    cycle = await reparent(client, company, current, north["id"], west["id"], dated(10))
    assert cycle.status_code == 422, cycle.text
    assert cycle.json()["error"]["code"] == "validation_failed"
    # The refusal is the point: the rejected append rolled back with the generation.
    after = await detail(client, company, current, f"/warehouse-groups/{north['id']}")
    assert after == before

    parent = west["id"]
    for depth in range(3, 9):
        parent = (await create_group(client, company, current, f"L{depth}", parent))["id"]
    refused = await client.post(
        f"/v1/companies/{company}/warehouse-groups",
        headers=command_headers(current),
        json={"code": "L9", "name": "L9", "parent_group_id": parent, "valid_from": PAST},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_failed"
    with tenant_scope(tenant_a):
        async with factory() as db:
            # Eight groups, eight opening intervals: the ninth create left nothing behind.
            assert await db.scalar(select(func.count(WarehouseGroup.id))) == 8
            assert await db.scalar(select(func.count(WarehouseGroupParent.id))) == 8
    # A group whose opening interval is missing is corrupt, not unparented: reparenting it
    # would have to invent the history it should have, so it is refused instead.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await db.execute(
                delete(WarehouseGroupParent).where(
                    WarehouseGroupParent.group_id == uuid.UUID(west["id"])
                )
            )
    orphaned = await reparent(client, company, current, west["id"], None, dated(10))
    assert orphaned.status_code == 409, orphaned.text
    assert orphaned.json()["error"]["message"] == "group has no current parent history"


async def test_dated_reparent_preserves_historical_rollups(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    soon, later = dated(10), dated(20)
    north = await create_group(client, company, current, "NORTH")
    south = await create_group(client, company, current, "SOUTH")
    west = await create_group(client, company, current, "WEST", north["id"])
    godown = await create_location(client, company, current, "GD1")
    assigned = await assign(client, company, current, godown, west["id"], soon)
    assert assigned.status_code == 200, assigned.text
    moved = await reparent(client, company, current, west["id"], south["id"], later)
    assert moved.status_code == 200, moved.text

    # The reparenting is dated, so each rollup answers for the date it was asked about.
    assert await members(client, company, current, north["id"], soon) == ["GD1"]
    assert await members(client, company, current, north["id"], later) == []
    assert await members(client, company, current, south["id"], soon) == []
    assert await members(client, company, current, south["id"], later) == ["GD1"]
    # Membership itself starts later than today; before that the location is in no group.
    assert await members(client, company, current, west["id"], dated(0)) == []
    assert await members(client, company, current, west["id"], soon) == ["GD1"]
    assert await children(client, company, current, north["id"], soon) == ["WEST"]
    assert await children(client, company, current, north["id"], later) == []
    assert await children(client, company, current, south["id"], later) == ["WEST"]

    history = await client.get(
        f"/v1/companies/{company}/warehouse-groups/{west['id']}/parents", headers=current
    )
    assert history.status_code == 200, history.text
    intervals = [
        (row["parent_group_id"], row["valid_from"], row["valid_to"])
        for row in history.json()["items"]
    ]
    closed = (dt.date.fromisoformat(later) - dt.timedelta(days=1)).isoformat()
    assert intervals == [
        (north["id"], PAST, closed),
        (south["id"], later, None),
    ]
    dated_history = await client.get(
        f"/v1/companies/{company}/warehouse-groups/{west['id']}/parents",
        headers=current,
        params={"valid_at": soon},
    )
    assert [row["parent_group_id"] for row in dated_history.json()["items"]] == [north["id"]]
    # Nothing was rewritten: the superseded interval is still there, closed the day before.
    with tenant_scope(tenant_a):
        async with factory() as db:
            rows = list(
                await db.scalars(
                    select(WarehouseGroupParent)
                    .where(WarehouseGroupParent.group_id == uuid.UUID(west["id"]))
                    .order_by(WarehouseGroupParent.valid_from)
                )
            )
    assert [row.valid_from.isoformat() for row in rows] == [PAST, later]
    assert rows[0].valid_to is not None and rows[0].valid_to.isoformat() == closed
    assert rows[1].valid_to is None


async def test_group_membership_grants_no_access_to_its_locations(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    own, other, user = uuid7(), uuid7(), uuid7()
    current = await auth(factory, tenant_a, own, user, permission=GROUPING)
    foreign = await auth(factory, tenant_a, other, uuid7(), permission=GROUPING)
    group = await create_group(client, own, current, "NORTH")
    godown = await create_location(client, own, current, "GD1")
    assigned = await assign(client, own, current, godown, group["id"], dated(10))
    assert assigned.status_code == 200, assigned.text
    # A group is an identity and a lifecycle. There is no scope, permission or location on it.
    assert set(group) == DETAIL_KEYS

    route = f"/v1/companies/{own}/warehouse-groups/{group['id']}/members"
    composition = headers(own, tenant=tenant_a, user=user, permission=["warehouse_group.read"])
    places = headers(own, tenant=tenant_a, user=user, permission=["warehouse.read"])
    for actor in (composition, places):
        # Reading the rollup is reading two things, and holding one of them is not enough.
        response = await client.get(route, headers=actor, params={"valid_at": dated(10)})
        assert response.status_code == 403, response.text
    assert (await client.get(route, params={"valid_at": dated(10)})).status_code == 401
    assert (await client.get(route, headers=current)).status_code == 422
    # Wrong company inside the tenant is forbidden; another tenant is not told it exists.
    assert (
        await client.get(
            f"/v1/companies/{other}/warehouse-groups/{group['id']}/members",
            headers=foreign,
            params={"valid_at": dated(10)},
        )
    ).status_code == 403
    alien = await auth(factory, tenant_b, own, uuid7(), permission=GROUPING)
    assert (
        await client.get(route, headers=alien, params={"valid_at": dated(10)})
    ).status_code == 404

    # Grouping a location is a grouping change over a location: it needs authority over both.
    location_only = headers(
        own, tenant=tenant_a, user=user, permission=["warehouse.read", "warehouse.manage"]
    )
    group_only = headers(
        own,
        tenant=tenant_a,
        user=user,
        permission=["warehouse_group.read", "warehouse_group.manage"],
    )
    for actor in (location_only, group_only):
        refused = await assign(client, own, actor, godown, group["id"], dated(30), reader=current)
        assert refused.status_code == 403, refused.text
    # Moving a group in the hierarchy is its own permission, not `manage`.
    mover_denied = headers(
        own,
        tenant=tenant_a,
        user=user,
        permission=["warehouse_group.read", "warehouse_group.manage"],
    )
    refused = await reparent(client, own, mover_denied, group["id"], None, dated(30))
    assert refused.status_code == 403, refused.text
    # A read-deny on a membership field blocks the rollup server-side, layout notwithstanding.
    blinded = await auth(
        factory,
        tenant_a,
        own,
        user,
        permission=GROUPING,
        version=3,
        extra=(denial(own, user, "catalog.warehouse_group_assignment", "group_id", "read"),),
    )
    hidden = await client.get(route, headers=blinded, params={"valid_at": dated(10)})
    assert hidden.status_code == 403, hidden.text


async def test_a_location_has_one_primary_group_on_any_date(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    north = await create_group(client, company, current, "NORTH")
    south = await create_group(client, company, current, "SOUTH")
    godown = await create_location(client, company, current, "GD1")
    configuration = await detail(client, company, current, "/warehouse-configuration")

    first = await assign(client, company, current, godown, north["id"], dated(10))
    assert first.status_code == 200, first.text
    assert first.json()["row_version"] == 2
    # Assigning the group it is already in changes nothing, so nothing is versioned.
    unchanged = await assign(client, company, current, godown, north["id"], dated(20))
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["row_version"] == 2
    assert unchanged.json()["policy_generation"] == first.json()["policy_generation"]
    # Two intervals may not start on one day, and history is never rewritten.
    same_day = await assign(client, company, current, godown, south["id"], dated(10))
    assert same_day.status_code == 409, same_day.text
    assert same_day.json()["error"]["message"].startswith("reparenting must append")
    past = await assign(client, company, current, godown, south["id"], dated(-1))
    assert past.status_code == 409, past.text

    second = await assign(client, company, current, godown, south["id"], dated(20))
    assert second.status_code == 200, second.text
    assert second.json()["row_version"] == 3
    cleared = await assign(client, company, current, godown, None, dated(30))
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["row_version"] == 4
    # "No group" is the absence of an open interval, never a row pointing at nothing.
    with tenant_scope(tenant_a):
        async with factory() as db:
            rows = list(
                await db.scalars(
                    select(WarehouseGroupAssignment).order_by(WarehouseGroupAssignment.valid_from)
                )
            )
    assert [(str(row.group_id), row.valid_from.isoformat()) for row in rows] == [
        (north["id"], dated(10)),
        (south["id"], dated(20)),
    ]
    assert [row.valid_to.isoformat() if row.valid_to else None for row in rows] == [
        dated(19),
        dated(29),
    ]
    # Clearing a membership that is already clear asks for nothing and writes nothing.
    again = await assign(client, company, current, godown, None, dated(35))
    assert again.status_code == 200 and again.json()["row_version"] == 4, again.text
    # A cleared location still has history, so an append may not reach back into it.
    overlapping = await assign(client, company, current, godown, north["id"], dated(25))
    assert overlapping.status_code == 409, overlapping.text
    # ... and it has no group, so it can be given one again.
    regrouped = await assign(client, company, current, godown, north["id"], dated(40))
    assert regrouped.status_code == 200, regrouped.text
    assert regrouped.json()["row_version"] == 5
    assert await members(client, company, current, north["id"], dated(40)) == ["GD1"]

    view = await detail(client, company, current, f"/warehouses/{godown}")
    stale = await assign(
        client, company, current, godown, south["id"], dated(50), version=view["row_version"] - 1
    )
    assert stale.status_code == 409, stale.text
    outdated = await assign(
        client,
        company,
        current,
        godown,
        south["id"],
        dated(50),
        generation=view["policy_generation"] - 1,
    )
    assert outdated.status_code == 409, outdated.text
    assert outdated.json()["error"]["message"] == "company policy changed; reload the hierarchy"
    # Transit is custody, not a place: it belongs to no reporting dimension.
    transit = await assign(
        client, company, current, str(configuration["transit_warehouse_id"]), north["id"], dated(50)
    )
    assert transit.status_code == 409, transit.text
    assert transit.json()["error"]["message"].startswith("internal transit custody")
    # A retired group is not somewhere new stock can be organised under.
    spare = await create_group(client, company, current, "SPARE")
    retired = await client.post(
        f"/v1/companies/{company}/warehouse-groups/{spare['id']}/deactivate",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert retired.status_code == 200, retired.text
    inactive = await assign(client, company, current, godown, spare["id"], dated(50))
    assert inactive.status_code == 409, inactive.text
    assert inactive.json()["error"]["message"] == "group parent is inactive"
    missing = await assign(client, company, current, godown, str(uuid7()), dated(50))
    assert missing.status_code == 404, missing.text
    # A group with members keeps its identity and lifecycle: something relies on both.
    referenced = await client.post(
        f"/v1/companies/{company}/warehouse-groups/{north['id']}/deactivate",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert referenced.status_code == 409, referenced.text
    assert referenced.json()["error"]["message"].startswith("classification is referenced")


async def test_a_group_is_never_somewhere_stock_can_be_put(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    group = await create_group(client, company, current, "NORTH")
    await create_location(client, company, current, "GD1")
    configuration = await detail(client, company, current, "/warehouse-configuration")
    main = str(configuration["main_warehouse_id"])
    identity = group["id"]
    before = await detail(client, company, current, f"/warehouse-groups/{identity}")
    # A group id is not a location id anywhere a location id is accepted.
    assert (
        await client.get(f"/v1/companies/{company}/warehouses/{identity}", headers=current)
    ).status_code == 404
    assert (
        await client.get(
            f"/v1/companies/{company}/warehouses/{identity}/operation-policy", headers=current
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/v1/companies/{company}/warehouse-bins",
            headers=command_headers(current),
            json={"code": "A1", "name": "Rack A1", "warehouse_id": identity},
        )
    ).status_code == 404
    grouped = await assign(
        client,
        company,
        current,
        identity,
        identity,
        dated(10),
        version=1,
        generation=configuration["policy_generation"],
    )
    assert grouped.status_code == 404, grouped.text
    pointers = dict.fromkeys(
        (
            "default_sale_warehouse_id",
            "default_purchase_warehouse_id",
            "default_customer_return_warehouse_id",
            "default_opening_warehouse_id",
        ),
        main,
    )
    refused = await client.post(
        f"/v1/companies/{company}/warehouse-configuration/defaults",
        headers=command_headers(current),
        json={
            **pointers,
            "default_sale_warehouse_id": identity,
            "expected_generation": configuration["policy_generation"],
            "expected_source_version": configuration["source_version"],
        },
    )
    assert refused.status_code == 404, refused.text
    # Nothing about the group changed on the way through any of those refusals.
    assert await detail(client, company, current, f"/warehouse-groups/{identity}") == before


async def test_bin_codes_are_unique_within_a_location_and_repeat_across_them(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    native_retirement,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    first = await create_location(client, company, current, "GD1")
    second = await create_location(client, company, current, "GD2")
    configuration = await detail(client, company, current, "/warehouse-configuration")
    route = f"/v1/companies/{company}/warehouse-bins"

    created = await client.post(
        route,
        headers=command_headers(current),
        json={"code": "A1", "name": "Rack A1", "warehouse_id": first},
    )
    assert created.status_code == 201, created.text
    assert set(created.json()) == DETAIL_KEYS | {"warehouse_id"}
    assert created.json()["warehouse_id"] == first
    duplicate = await client.post(
        route,
        headers=command_headers(current),
        json={"code": "A1", "name": "Other rack", "warehouse_id": first},
    )
    assert duplicate.status_code == 409, duplicate.text
    # `A1` in another godown is a different bin, not a duplicate: the location is its identity.
    elsewhere = await client.post(
        route,
        headers=command_headers(current),
        json={"code": "A1", "name": "Rack A1", "warehouse_id": second},
    )
    assert elsewhere.status_code == 201, elsewhere.text
    assert (
        await client.post(
            route,
            headers=command_headers(current),
            json={
                "code": "A1",
                "name": "Custody rack",
                "warehouse_id": str(configuration["transit_warehouse_id"]),
            },
        )
    ).status_code == 409

    identity = created.json()["id"]
    # A bin never moves. `warehouse_id` is not on the update surface at all.
    assert (
        await client.patch(
            f"{route}/{identity}",
            headers=command_headers(current),
            json={"expected_version": 1, "warehouse_id": second},
        )
    ).status_code == 422
    renamed = await client.patch(
        f"{route}/{identity}",
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Rack A1 north"},
    )
    assert renamed.status_code == 200, renamed.text

    listed = await client.get(route, headers=current, params={"warehouse_id": second})
    assert [row["code"] for row in listed.json()["items"]] == ["A1"]
    assert len((await client.get(route, headers=current)).json()["items"]) == 2

    # A location keeps its bins' parent honest in both directions: retire the bins first.
    target = f"/v1/companies/{company}/warehouses/{second}"
    blocked = await client.post(
        target + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["message"].startswith("retire the location's bins")
    assert (
        await client.post(
            f"{route}/{elsewhere.json()['id']}/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    # With its last bin retired the location clears Catalog's half of the fence, and the
    # coordinated half is satisfied the only way it can be: a published release and Billing's
    # clearance against it (docs/catalog-warehouses.md §5).
    emptied = await retire(client, factory, tenant_a, company, second, current)
    assert emptied.status_code == 200, emptied.text
    # A bin cannot be created in, or brought back into, a location that is retired.
    assert (
        await client.post(
            route,
            headers=command_headers(current),
            json={"code": "B1", "name": "Rack B1", "warehouse_id": second},
        )
    ).status_code == 409
    revived = await client.post(
        f"{route}/{elsewhere.json()['id']}/activate",
        headers=command_headers(current),
        json={"expected_version": 2},
    )
    assert revived.status_code == 409, revived.text
    assert revived.json()["error"]["message"] == "bin location is inactive"


async def test_grouping_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """One company id in two tenants. Each tenant's session sees only its own four rows."""
    company = uuid7()
    for tenant in (tenant_a, tenant_b):
        main, _ = await seed_locations(factory, tenant, company)
        with tenant_scope(tenant):
            async with factory.begin() as db:
                group = WarehouseGroup(
                    id=uuid7(),
                    tenant_id=tenant,
                    company_id=company,
                    code="NORTH",
                    name="North",
                    is_active=True,
                    row_version=1,
                )
                db.add(group)
                await db.flush()
                db.add_all(
                    [
                        WarehouseGroupParent(
                            id=uuid7(),
                            tenant_id=tenant,
                            company_id=company,
                            group_id=group.id,
                            parent_group_id=None,
                            valid_from=dt.date(2020, 1, 1),
                            valid_to=None,
                        ),
                        WarehouseGroupAssignment(
                            id=uuid7(),
                            tenant_id=tenant,
                            company_id=company,
                            warehouse_id=main,
                            group_id=group.id,
                            valid_from=dt.date(2020, 1, 1),
                            valid_to=None,
                        ),
                        WarehouseBin(
                            id=uuid7(),
                            tenant_id=tenant,
                            company_id=company,
                            warehouse_id=main,
                            code="A1",
                            name="Rack A1",
                            is_active=True,
                            row_version=1,
                        ),
                    ]
                )
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            async with factory() as db:
                models: tuple[type[Any], ...] = (
                    WarehouseGroup,
                    WarehouseGroupParent,
                    WarehouseGroupAssignment,
                    WarehouseBin,
                )
                for model in models:
                    rows: list[Any] = list(await db.scalars(select(model)))
                    assert len(rows) == 1, model.__name__
                    assert {row.tenant_id for row in rows} == {tenant}
                    assert {row.company_id for row in rows} == {company}


async def test_one_membership_may_start_on_a_date_whatever_wrote_the_row(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """The rollup's no-double-counting rule is a schema fact, not only a command rule."""
    company = uuid7()
    main, _ = await seed_locations(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            groups = [
                WarehouseGroup(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    code=code,
                    name=code.title(),
                    is_active=True,
                    row_version=1,
                )
                for code in ("NORTH", "SOUTH")
            ]
            db.add_all(groups)
            await db.flush()
            db.add(
                WarehouseGroupAssignment(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    warehouse_id=main,
                    group_id=groups[0].id,
                    valid_from=dt.date(2020, 1, 1),
                    valid_to=None,
                )
            )
            second = groups[1].id
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(
                WarehouseGroupAssignment(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    warehouse_id=main,
                    group_id=second,
                    valid_from=dt.date(2020, 1, 1),
                    valid_to=None,
                )
            )
            await db.flush()


async def test_grouping_routes_are_permissioned_and_closed(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    group = await create_group(client, company, current, "NORTH")
    godown = await create_location(client, company, current, "GD1")
    created = await client.post(
        f"/v1/companies/{company}/warehouse-bins",
        headers=command_headers(current),
        json={"code": "A1", "name": "Rack A1", "warehouse_id": godown},
    )
    assert created.status_code == 201, created.text
    before = await detail(client, company, current, f"/warehouse-groups/{group['id']}")
    reader = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["warehouse.read", "warehouse_group.read", "warehouse_bin.read"],
    )
    unpermitted = headers(company, tenant=tenant_a, user=user, permission="item.read")
    today = dated(0)
    reads: tuple[tuple[str, dict[str, str]], ...] = (
        ("/warehouse-groups", {}),
        (f"/warehouse-groups/{group['id']}", {}),
        (f"/warehouse-groups/{group['id']}/parents", {}),
        (f"/warehouse-groups/{group['id']}/children", {"valid_at": today}),
        (f"/warehouse-groups/{group['id']}/members", {"valid_at": today}),
        ("/warehouse-bins", {}),
        (f"/warehouse-bins/{created.json()['id']}", {}),
    )
    for path, params in reads:
        base = f"/v1/companies/{company}{path}"
        assert (await client.get(base, params=params)).status_code == 401, path
        assert (await client.get(base, headers=unpermitted, params=params)).status_code == 403, path
        assert (await client.get(base, headers=reader, params=params)).status_code == 200, path
        broken = await client.get(base, headers=reader, params={**params, "unknown": "x"})
        assert broken.status_code == 422, path
    groups = f"/v1/companies/{company}/warehouse-groups"
    listed = await client.get(groups, headers=reader, params={"is_active": "true", "q": "North"})
    assert [row["code"] for row in listed.json()["items"]] == ["NORTH"]
    assert (await client.get(groups, headers=reader, params={"is_active": "false"})).json()[
        "items"
    ] == []
    rejected: tuple[dict[str, Any], ...] = (
        {"limit": 0},
        {"limit": 201},
        {"sort": "city"},
        {"is_active": "maybe"},
        {"code": ""},
    )
    for query in rejected:
        response = await client.get(groups, headers=reader, params=query)
        assert response.status_code == 422, query
    # The dated browsing endpoints never default their date.
    for path in ("children", "members"):
        response = await client.get(
            f"/v1/companies/{company}/warehouse-groups/{group['id']}/{path}", headers=reader
        )
        assert response.status_code == 422, path

    writes: tuple[tuple[str, str, dict[str, Any]], ...] = (
        ("POST", "/warehouse-groups", {"code": "X1", "name": "X1", "valid_from": PAST}),
        (
            "PATCH",
            f"/warehouse-groups/{group['id']}",
            {"expected_version": 1, "name": "Renamed"},
        ),
        ("POST", f"/warehouse-groups/{group['id']}/activate", {"expected_version": 1}),
        ("POST", f"/warehouse-groups/{group['id']}/deactivate", {"expected_version": 1}),
        (
            "POST",
            f"/warehouse-groups/{group['id']}/reparent",
            {
                "expected_version": 1,
                "expected_generation": 1,
                "parent_group_id": None,
                "effective_from": dated(10),
            },
        ),
        (
            "PUT",
            f"/warehouses/{godown}/primary-group",
            {
                "expected_version": 1,
                "expected_generation": 1,
                "group_id": group["id"],
                "effective_from": dated(10),
            },
        ),
        ("POST", "/warehouse-bins", {"code": "B1", "name": "Rack B1", "warehouse_id": godown}),
        (
            "PATCH",
            f"/warehouse-bins/{created.json()['id']}",
            {"expected_version": 1, "name": "Renamed"},
        ),
        (
            "POST",
            f"/warehouse-bins/{created.json()['id']}/deactivate",
            {"expected_version": 1},
        ),
    )
    for method, path, body in writes:
        base = f"/v1/companies/{company}{path}"
        assert (await client.request(method, base, json=body)).status_code == 401, path
        forbidden = await client.request(method, base, headers=command_headers(reader), json=body)
        assert forbidden.status_code == 403, (path, forbidden.text)
        # Every command needs its idempotency key, and no command accepts an unknown field.
        assert (
            await client.request(method, base, headers=current, json=body)
        ).status_code == 422, path
        extra = await client.request(
            method, base, headers=command_headers(current), json={**body, "unknown": "x"}
        )
        assert extra.status_code == 422, (path, extra.text)
    # None of that reached a row.
    assert await detail(client, company, current, f"/warehouse-groups/{group['id']}") == before
