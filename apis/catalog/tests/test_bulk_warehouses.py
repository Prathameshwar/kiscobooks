"""Every stock-location write a reviewed file may carry, and the ones it may not.

docs/catalog-warehouse-plan.md C10.09, docs/catalog-warehouses.md §2, §3, §5. A bulk row is not
a second write path: each adapter is the command the route calls, so the dated append, the
narrowing check, the generation guard and the built-in's reserved identity hold for a
spreadsheet exactly as they hold for a request. Four claims carry this file, and three of them
are refusals:

* one file may build the whole network — groups, their dated parent, a location, its bins and
  the location's dated primary group — and every rollup afterwards answers as if each row had
  arrived as its own request;
* a location's reviewed policy publishes for the code the row names, and a product's stocking
  rules and replenishment bands import by SKU, with no generation and no revision in the file:
  the guards are read at write time, so a file cannot echo back a picture nobody saw;
* what Billing owns has **no resource at all** — naming a stock balance, a transfer or a count
  is refused when the file is staged rather than dropped when it commits;
* the coordinated retirement fence, the provisioning singleton and the built-in location's
  identity are not bulk work either, and authority is resolved when the file runs: a publish
  key withheld after staging fails the record instead of publishing.
"""

import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item
from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouse_policies import ITEM_WIDE_SCOPE, ItemReplenishmentPolicy
from catalog.models.warehouses import Warehouse
from tests.bulk_factories import post, run
from tests.test_bulk_adapters import ref, row
from tests.test_bulk_products_prices import reviewed_commit
from tests.test_warehouse_groups import PAST, children, dated, members
from tests.test_warehouse_policies import ALL_TRUE, band, kinds, provision, read

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")

#: The company Identity checkpoint ``provision`` seeds. The worker's authorization proof has to
#: name the same one, so a job whose fixture advanced the source is refused rather than applied.
SOURCE_VERSION = 3
#: Everything Catalog exposes; the denials these tests care about are the worker's, which is
#: where a bulk row's authority is actually resolved (``tasks/bulk_matching.prepare``).
EVERYTHING = sorted(CATALOG_PERMISSIONS)


def coded(
    key: str, resource: str, code: str, data: dict[str, Any], *, action: str
) -> dict[str, Any]:
    """A row that addresses an existing target the way a spreadsheet does: by exact code."""
    return {**row(key, resource, data, action=action), "target": {"code": code}}


def grouping(code: str, name: str, *, parent: dict[str, str] | None = None) -> dict[str, Any]:
    """A group create. ``valid_from`` is required, so the hierarchy has a history from row one."""
    return {"code": code, "name": name, "parent_group_id": parent, "valid_from": PAST}


async def bulk(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Stage a file and hand back the validated job. ``UPSERT`` because these rows address
    locations and products that already exist, by their own codes rather than by staged keys."""
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(
        client, root, auth, "", {"format": "JSON", "mode": "UPSERT", "records": records}
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    return job


async def failed_record(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    auth: dict[str, str],
    record: dict[str, Any],
    *,
    denied: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Run a one-row file that must not apply, and return the reviewer's report for the row."""
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await bulk(client, company, auth, [record])
    state = await run(
        factory, tenant, company, user, job["id"], version=SOURCE_VERSION, denied=denied
    )
    assert state == "FAILED", state
    rows = (await client.get(root + "/" + job["id"] + "/records", headers=auth)).json()["items"]
    detail = await client.get(root + "/" + job["id"] + "/records/" + rows[0]["id"], headers=auth)
    assert detail.status_code == 200, detail.text
    return dict(detail.json())


async def test_a_whole_location_network_imports_through_the_dated_native_commands(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Groups, a location, a bin, a membership and a reparenting, in one reviewed change set.

    The two dated rows are the point: they append an interval and close the one in force, so
    the rollups keep answering for the date they are asked about — which a bulk row that wrote
    the pointer columns directly could not do (§3).
    """
    context = await provision(client, factory, tenant_a, permission=EVERYTHING)
    company, user, current = context["company"], context["user"], context["current"]
    soon, later = dated(10), dated(20)
    records = [
        row("region", "warehouse_group", grouping("REGION", "Region north"), group="network"),
        row("south", "warehouse_group", grouping("SOUTH", "Region south"), group="network"),
        row(
            "zone",
            "warehouse_group",
            grouping("ZONE", "Zone one", parent=ref("region")),
            group="network",
        ),
        row(
            "store",
            "warehouse",
            {"code": "GD1", "name": "Godown one", "kind": "GODOWN"},
            group="network",
        ),
        row(
            "rack",
            "warehouse_bin",
            {"code": "A1", "name": "Rack A1", "warehouse_id": ref("store")},
            group="network",
        ),
        row(
            "assign",
            "warehouse",
            {"group_id": ref("zone"), "effective_from": soon},
            action="ASSIGN",
            target="store",
            group="network",
        ),
        row(
            "move",
            "warehouse_group",
            {"parent_group_id": ref("south"), "effective_from": later},
            action="MOVE",
            target="zone",
            group="network",
        ),
    ]
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        current,
        {"format": "JSON", "records": records},
        version=SOURCE_VERSION,
    )

    with tenant_scope(tenant_a):
        async with factory() as db:
            groups: dict[str, uuid.UUID] = {}
            for code, identifier in (
                await db.execute(select(WarehouseGroup.code, WarehouseGroup.id))
            ).all():
                groups[code] = identifier
            store = await db.scalar(select(Warehouse.id).where(Warehouse.code == "GD1"))
            intervals = [
                (edge.parent_group_id, edge.valid_from.isoformat())
                for edge in (
                    await db.scalars(
                        select(WarehouseGroupParent)
                        .where(WarehouseGroupParent.group_id == groups["ZONE"])
                        .order_by(WarehouseGroupParent.valid_from)
                    )
                ).all()
            ]
            memberships = [
                (edge.group_id, edge.valid_from.isoformat(), edge.valid_to)
                for edge in (await db.scalars(select(WarehouseGroupAssignment))).all()
            ]
    # History was appended, not rewritten: the opening interval survives the reparenting.
    assert intervals == [(groups["REGION"], PAST), (groups["SOUTH"], later)]
    assert memberships == [(groups["ZONE"], soon, None)]

    region, south, zone = (str(groups[code]) for code in ("REGION", "SOUTH", "ZONE"))
    assert await members(client, company, current, region, soon) == ["GD1"]
    assert await members(client, company, current, region, later) == []
    assert await members(client, company, current, south, later) == ["GD1"]
    # The membership itself starts later than today, so before that the location is in no group.
    assert await members(client, company, current, zone, dated(0)) == []
    assert await children(client, company, current, region, soon) == ["ZONE"]
    assert await children(client, company, current, south, later) == ["ZONE"]

    bins = await read(client, f"/v1/companies/{company}/warehouse-bins", current)
    assert [(item["code"], item["warehouse_id"]) for item in bins["items"]] == [("A1", str(store))]


async def test_a_location_policy_and_a_products_stocking_rules_import_by_their_own_codes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A publish for a location the same file created, then the product policy that narrows it.

    Nothing in the file carries a generation, a source version or a revision number: those are
    read when the row is written, which is what makes a stale file a refusal rather than a
    silent overwrite of somebody else's reviewed policy (§2).
    """
    context = await provision(client, factory, tenant_a, permission=EVERYTHING)
    company, user, current = context["company"], context["user"], context["current"]
    item, binding = context["item"], context["binding"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            sku = await db.scalar(select(Item.sku).where(Item.id == uuid.UUID(item)))
    assert isinstance(sku, str)

    records = [
        row(
            "gd",
            "warehouse",
            {"code": "GD1", "name": "Godown one", "kind": "GODOWN"},
            group="stocking",
        ),
        row(
            "policy",
            "warehouse",
            {**ALL_TRUE, "allow_adjustment": False},
            action="PUBLISH_OPERATION_POLICY",
            target="gd",
            group="stocking",
        ),
        {
            **coded(
                "stock",
                "item",
                sku,
                {
                    "selection_mode": "ALLOW_LIST",
                    "default_sale_warehouse_id": None,
                    "default_purchase_warehouse_id": ref("gd"),
                    "default_customer_return_warehouse_id": None,
                    "default_opening_warehouse_id": None,
                    "locations": [
                        {"warehouse_id": ref("gd"), **ALL_TRUE, "allow_adjustment": False}
                    ],
                },
                action="SET_WAREHOUSE_POLICY",
            ),
            "change_set": "stocking",
            "depends_on": ["policy"],
        },
        {
            **coded(
                "bands",
                "item",
                sku,
                {
                    "scopes": [
                        {**band(binding), "warehouse_id": ref("gd")},
                        band(binding),
                    ]
                },
                action="SET_REPLENISHMENT_POLICY",
            ),
            "change_set": "stocking",
            "depends_on": ["stock"],
        },
    ]
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        current,
        {"format": "JSON", "mode": "UPSERT", "records": records},
        version=SOURCE_VERSION,
    )

    with tenant_scope(tenant_a):
        async with factory() as db:
            location = await db.scalar(select(Warehouse.id).where(Warehouse.code == "GD1"))
            bands = (
                await db.scalars(
                    select(ItemReplenishmentPolicy).order_by(
                        ItemReplenishmentPolicy.scope_warehouse_id
                    )
                )
            ).all()
    assert isinstance(location, uuid.UUID)

    # Revision 1 is what the create inherited from the built-in Main; revision 2 is the publish.
    view = await read(
        client, f"/v1/companies/{company}/warehouses/{location}/operation-policy", current
    )
    assert view["current"]["revision"] == 2
    assert view["current"]["allow_adjustment"] is False
    assert view["current"]["allow_purchase_receipt"] is True

    policy = await read(client, f"/v1/companies/{company}/items/{item}/warehouse-policy", current)
    assert policy["is_configured"] is True
    assert policy["selection_mode"] == "ALLOW_LIST"
    assert policy["default_purchase_warehouse_id"] == str(location)
    assert [
        (entry["warehouse_id"], entry["effective_operations"]) for entry in policy["locations"]
    ] == [(str(location), kinds("allow_adjustment"))]

    # A band with no location is the product-wide one, and it is a stored sentinel rather than a
    # NULL: "exactly one" is then a unique constraint instead of a convention.
    assert {scope.scope_warehouse_id for scope in bands} == {location, ITEM_WIDE_SCOPE}
    assert {scope.warehouse_id for scope in bands} == {location, None}
    for scope in bands:
        assert isinstance(scope.target_quantity, Decimal)
        assert (scope.target_quantity, scope.order_multiple) == (Decimal("20"), Decimal("10"))
        assert scope.purchase_binding_id == uuid.UUID(binding)


async def test_the_facts_and_the_coordinated_actions_catalog_does_not_own_have_no_resource(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A name nothing registered is refused at staging, before a reviewer sees a plan.

    Refusing here rather than per row is deliberate: a quantity, a count sheet, a transfer and a
    trading party are all somebody else's, and a file whose header says otherwise has to be
    corrected rather than partly applied (docs/catalog-warehouses.md §1). The retirement fence and
    the provisioning singleton are absent for a different reason — both are one reviewed,
    coordinated action, and a file of them is exactly what a fence exists to prevent.
    """
    context = await provision(client, factory, tenant_a, permission=EVERYTHING)
    company, user, current = context["company"], context["user"], context["current"]
    root = f"/v1/companies/{company}/bulk-jobs"
    for resource, action in (
        ("warehouse_stock_balance", "CREATE"),
        ("stock_transfer", "CREATE"),
        ("physical_count", "CREATE"),
        ("supplier", "CREATE"),
        ("party", "CREATE"),
        ("warehouse", "DEACTIVATE"),
        ("company_warehouse_configuration", "SET_DEFAULTS"),
        ("warehouse_bin", "MOVE"),
        ("warehouse_group", "ASSIGN"),
    ):
        refused = await client.post(
            root,
            headers={**current, "Idempotency-Key": str(uuid7())},
            json={
                "format": "JSON",
                "records": [row("r1", resource, {"code": "X", "name": "X"}, action=action)],
            },
        )
        assert refused.status_code == 422, (resource, action, refused.text)
        assert refused.json()["error"]["message"] == (
            "resource or action is not available for Catalog bulk work"
        )

    # The built-in location is addressable — it is a real store — but its identity is reserved,
    # so the same refusal the API gives becomes this row's review conflict.
    conflict = await failed_record(
        client,
        factory,
        tenant_a,
        company,
        user,
        current,
        coded("main", "warehouse", "MAIN", {"code": "HUB"}, action="UPDATE"),
    )
    assert conflict["error_code"] == "review_conflict"
    # A quantity cannot ride in on a location row either: the schema forbids it, and the report
    # names the column so the author knows which one to delete.
    facts = await failed_record(
        client,
        factory,
        tenant_a,
        company,
        user,
        current,
        row(
            "facts",
            "warehouse",
            {"code": "GD9", "name": "Godown nine", "kind": "GODOWN", "on_hand": "12"},
        ),
    )
    assert facts["error_code"] == "invalid_record"
    assert facts["error_fields"] == ["on_hand"]

    with tenant_scope(tenant_a):
        async with factory() as db:
            codes = sorted(await db.scalars(select(Warehouse.code)))
    assert codes == ["MAIN", "TRANSIT"]


async def test_a_publish_key_withheld_after_staging_fails_the_row_not_the_policy(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Authority is resolved when the file runs, and before its target is even looked up.

    A file staged while the actor could publish must not publish once that key is gone: the
    reviewed plan is a proposal, never a stored permission (CLAUDE.md §5.4).
    """
    context = await provision(client, factory, tenant_a, permission=EVERYTHING)
    company, user, current = context["company"], context["user"], context["current"]
    created = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers={**current, "Idempotency-Key": str(uuid7())},
        json={"code": "GD1", "name": "Godown one", "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    location = created.json()["id"]

    report = await failed_record(
        client,
        factory,
        tenant_a,
        company,
        user,
        current,
        coded(
            "policy",
            "warehouse",
            "GD1",
            {**ALL_TRUE, "allow_adjustment": False},
            action="PUBLISH_OPERATION_POLICY",
        ),
        denied=frozenset({"warehouse.publish"}),
    )
    assert report["error_code"] == "permission_denied"

    # Nothing published: the location still holds the revision it inherited at creation.
    view = await read(
        client, f"/v1/companies/{company}/warehouses/{location}/operation-policy", current
    )
    assert view["current"]["revision"] == 1
    assert view["current"]["allow_adjustment"] is True
