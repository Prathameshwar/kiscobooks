"""Per-product stock-location policies and replenishment bands over HTTP and in storage.

docs/catalog-warehouses.md §2, §3, §5. Four claims carry this surface, and each is asserted
as a refusal rather than as a convenience:

* a product policy **narrows** the location's reviewed policy and never widens it, in either
  order the two are stated;
* a **missing row is the documented baseline** — adding these tables changed no product's
  reach, and the read says so rather than inventing a configured answer;
* a **stock location is for stock**: a service, or goods a type calls non-stock, is refused;
* every quantity lands on the ordering unit's own grid, and a location a product is still
  stocked at cannot be retired underneath it.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.warehouse_resolution import OPERATIONS
from catalog.domain.warehouses import OPERATION_FLAGS
from catalog.events.audit_contract import AUDIT_EVENTS
from catalog.models import Item, Outbox, ProductFamily, ProductType, ProductTypeRevision
from catalog.models.warehouse_policies import (
    ITEM_WIDE_SCOPE,
    ItemReplenishmentPolicy,
    ItemWarehousePermission,
    ItemWarehousePolicy,
)
from tests.product_definition_factories import seed_definitions
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import MULTI, auth
from tests.warehouse_factories import retire as retire_location

#: What a stock administrator holds. The manage key is what these writes cost; the reader
#: keys are demanded because every one of these paths resolves the product, the company's
#: locations, and — for a band — the product's own membership. ``warehouse.publish`` is here
#: so a test can narrow a *location's* reviewed policy first and publish the release retirement
#: needs; ``warehouse.deactivate`` and ``catalog.release.read`` are what retiring one costs.
STOCK: tuple[str, ...] = (
    "item.read",
    "warehouse.read",
    "warehouse.manage",
    "warehouse.publish",
    "warehouse.deactivate",
    "catalog.release.read",
    "item_warehouse_policy.read",
    "item_warehouse_policy.manage",
)
#: Reading these projections needs the policy read key *and* ``warehouse.read``: the views
#: answer with location identities (docs/field-permissions.md §6).
READER: tuple[str, ...] = ("item.read", "warehouse.read", "item_warehouse_policy.read")

ALL_TRUE: dict[str, bool] = dict.fromkeys(OPERATION_FLAGS, True)
#: ``Any`` because the three share only ``PricingRow``, and what these tests query is the
#: ``item_id`` each one declares for itself.
POLICY_TABLES: tuple[Any, ...] = (
    ItemWarehousePolicy,
    ItemWarehousePermission,
    ItemReplenishmentPolicy,
)


def kinds(*denied: str) -> list[str]:
    """The composed operation kinds left once ``denied`` flags are taken away."""
    return sorted(kind for kind, flag in OPERATIONS.items() if flag not in denied)


def policy_route(company: uuid.UUID, item: str) -> str:
    return f"/v1/companies/{company}/items/{item}/warehouse-policy"


def band_route(company: uuid.UUID, item: str) -> str:
    return f"/v1/companies/{company}/items/{item}/replenishment-policy"


def guard(view: dict[str, Any]) -> dict[str, Any]:
    """The picture the reviewer read, echoed back so a concurrent change is a refusal."""
    return {
        "expected_generation": view["policy_generation"],
        "expected_source_version": view["source_version"],
    }


def entry(warehouse: str, **changes: bool) -> dict[str, Any]:
    return {"warehouse_id": warehouse, **ALL_TRUE, **changes}


def policy_body(
    view: dict[str, Any],
    *,
    mode: str = "ALLOW_LIST",
    locations: Sequence[dict[str, Any]] = (),
    **defaults: Any,
) -> dict[str, Any]:
    """The whole policy: the mode, the membership and the four activity defaults."""
    body: dict[str, Any] = {
        "selection_mode": mode,
        "default_sale_warehouse_id": None,
        "default_purchase_warehouse_id": None,
        "default_customer_return_warehouse_id": None,
        "default_opening_warehouse_id": None,
        "locations": list(locations),
        **guard(view),
    }
    body.update(defaults)
    return body


def band(binding: str, *, warehouse: str | None = None, **changes: Any) -> dict[str, Any]:
    """A band that fits the seeded unit grid: whole numbers, ordered in tens."""
    scope: dict[str, Any] = {
        "warehouse_id": warehouse,
        "purchase_binding_id": binding,
        "safety_quantity": "2",
        "reorder_quantity": "5",
        "target_quantity": "20",
        "min_order_quantity": "10",
        "max_order_quantity": "100",
        "order_multiple": "10",
        "lead_time_days": 7,
    }
    scope.update(changes)
    return scope


def denial(
    company: uuid.UUID, user: uuid.UUID, entity: str, field: str, access: str
) -> SnapshotRecord:
    """One Identity field policy denying this user one field, tenant-wide."""
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


async def read(client: httpx.AsyncClient, path: str, current: dict[str, str]) -> dict[str, Any]:
    response = await client.get(path, headers=current)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def provision(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    features: Sequence[str] = MULTI,
    permission: Sequence[str] = STOCK,
    extra: Sequence[SnapshotRecord] = (),
) -> dict[str, Any]:
    """A company with a stocked product, its unit definitions and its built-in locations."""
    company, ids = await seed_definitions(factory, tenant)
    current = await auth(
        factory,
        tenant,
        company,
        ids["actor_user"],
        features=features,
        permission=permission,
        version=3,
        extra=extra,
    )
    created = await client.post(
        f"/v1/companies/{company}/warehouse-configuration/bootstrap",
        headers=command_headers(current),
        json={},
    )
    assert created.status_code == 201, created.text
    return {
        "company": company,
        "user": ids["actor_user"],
        "item": str(ids["item"]),
        "binding": str(ids["item_unit_binding"]),
        "current": current,
        "config": await read(client, f"/v1/companies/{company}/warehouse-configuration", current),
    }


async def location(
    client: httpx.AsyncClient, company: uuid.UUID, current: dict[str, str], code: str
) -> str:
    created = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(current),
        json={"code": code, "name": code.title(), "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def publish_operations(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    warehouse: str,
    current: dict[str, str],
    **changes: bool,
) -> None:
    """Narrow one location's own reviewed policy — the ceiling a product policy sits under."""
    target = f"/v1/companies/{company}/warehouses/{warehouse}/operation-policy"
    view = await read(client, target, current)
    published = await client.post(
        target + "/publish",
        headers=command_headers(current),
        json={**ALL_TRUE, **changes, **guard(view)},
    )
    assert published.status_code == 201, published.text


async def stored(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, model: type[Any], item: str
) -> list[Any]:
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(model).where(model.item_id == uuid.UUID(item)).order_by(model.id)
                )
            )


async def emitted(factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID) -> list[Outbox]:
    """This tenant's product-policy events, ``tenant_id`` stated: ``outbox`` is exempt from the
    session tenant filter, so the scope alone would read every tenant's rows."""
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(Outbox)
                    .where(
                        Outbox.tenant_id == tenant,
                        Outbox.event_type.startswith("catalog.item_warehouse"),
                    )
                    .order_by(Outbox.id)
                )
            )


async def typed_item(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    reference: str,
    *,
    kind: str,
    modes: Sequence[str],
    code: str,
) -> str:
    """A second product in the same company, typed as the test needs it.

    Built directly because the point is the *type*: the authoring API would refuse some of
    these combinations for its own reasons, and this suite is asserting what the location
    policy does with a product that is not stock.
    """
    with tenant_scope(tenant):
        async with factory.begin() as db:
            common: dict[str, Any] = {"tenant_id": tenant, "company_id": company}
            base_unit = await db.scalar(
                select(Item.base_unit_id).where(Item.id == uuid.UUID(reference))
            )
            assert base_unit is not None
            owner = ProductType(id=uuid7(), code=code, name=code.title(), kind=kind, **common)
            db.add(owner)
            await db.flush()
            revision = ProductTypeRevision(
                id=uuid7(),
                product_type_id=owner.id,
                revision=1,
                kind=kind,
                inventory_modes=list(modes),
                tracking_modes=["NONE"],
                unit_dimensions=["COUNT"],
                allow_variants=False,
                require_brand=False,
                require_manufacturer=False,
                require_expiry=False,
                published_at=utcnow(),
                **common,
            )
            db.add(revision)
            await db.flush()
            family = ProductFamily(
                id=uuid7(),
                code=code + "F",
                name=code.title(),
                kind=kind,
                product_type_revision_id=revision.id,
                structure_mode="SIMPLE",
                status="DRAFT",
                **common,
            )
            db.add(family)
            await db.flush()
            item = Item(
                id=uuid7(),
                family_id=family.id,
                default_slot=1,
                sku=code + "SKU",
                name=code.title(),
                base_unit_id=base_unit,
                sellable=True,
                purchasable=True,
                status="DRAFT",
                **common,
            )
            db.add(item)
            await db.flush()
            return str(item.id)


async def test_a_product_policy_narrows_a_location_and_the_view_composes_it(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """The intersection, proved in both orders: the product is narrowed against a permissive
    location, then the location is narrowed under an unchanged product row."""
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    main = fixture["config"]["main_warehouse_id"]
    godown = await location(client, company, current, "GD1")
    target = policy_route(company, item)

    baseline = await read(client, target, current)
    assert baseline["is_configured"] is False
    assert baseline["selection_mode"] == "ALLOW_ALL_ACTIVE"
    assert baseline["locations"] == []
    for model in POLICY_TABLES:
        assert await stored(factory, tenant_a, model, item) == []

    body = policy_body(
        baseline,
        locations=[entry(main), entry(godown, allow_sale_issue=False, allow_adjustment=False)],
        default_purchase_warehouse_id=godown,
    )
    receipt = command_headers(current)
    written = await client.put(target, headers=receipt, json=body)
    assert written.status_code == 200, written.text
    assert written.headers["Idempotency-Replayed"] == "false"
    assert written.headers["Cache-Control"] == "no-store"
    result = written.json()
    assert result["row_version"] == 1
    assert result["policy_generation"] == baseline["policy_generation"] + 1
    replay = await client.put(target, headers=receipt, json=body)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == result
    assert len(await stored(factory, tenant_a, ItemWarehousePermission, item)) == 2

    view = await read(client, target, current)
    assert view["is_configured"] is True and view["selection_mode"] == "ALLOW_LIST"
    assert view["default_purchase_warehouse_id"] == godown
    assert view["default_sale_warehouse_id"] is None
    assert view["policy_generation"] == result["policy_generation"]
    entries = {detail["warehouse_id"]: detail for detail in view["locations"]}
    assert set(entries) == {main, godown}
    assert entries[main]["effective_operations"] == kinds()
    assert entries[main]["location_revision"] == 1
    assert entries[godown]["allow_sale_issue"] is False
    assert entries[godown]["allow_purchase_receipt"] is True
    assert entries[godown]["is_active"] is True
    assert entries[godown]["effective_operations"] == kinds("allow_sale_issue", "allow_adjustment")

    # The other order: the *location* is narrowed afterwards. The product row is untouched
    # and the composition shrinks, because the intersection is not a stored value.
    await publish_operations(client, company, godown, current, allow_purchase_receipt=False)
    composed = await read(client, target, current)
    narrowed = next(detail for detail in composed["locations"] if detail["warehouse_id"] == godown)
    assert narrowed["allow_purchase_receipt"] is True
    assert narrowed["location_revision"] == 2
    assert narrowed["effective_operations"] == kinds(
        "allow_sale_issue", "allow_adjustment", "allow_purchase_receipt"
    )
    rows = await stored(factory, tenant_a, ItemWarehousePermission, item)
    assert {row.row_version for row in rows} == {1}

    events = await emitted(factory, tenant_a)
    assert [row.event_type for row in events] == [
        "catalog.item_warehouse_policy.create",
        "catalog.item_warehouse_permission.create",
        "catalog.item_warehouse_permission.create",
    ]
    assert {row.event_type for row in events} <= AUDIT_EVENTS
    assert events[0].payload["changes"]["selection_mode"] == {"from": None, "to": "ALLOW_LIST"}
    assert events[0].payload["company_id"] == str(company)
    assert events[0].payload["category"] == "admin"
    assert events[2].payload["changes"]["allow_sale_issue"] == {"from": None, "to": "false"}


async def test_a_product_policy_cannot_allow_what_the_location_does_not(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Refused, never trimmed: the stored flags mean what the reviewer ticked (§2)."""
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    godown = await location(client, company, current, "GD1")
    await publish_operations(client, company, godown, current, allow_sale_issue=False)
    target = policy_route(company, item)
    view = await read(client, target, current)

    widened = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(godown)]),
    )
    assert widened.status_code == 409, widened.text
    assert (
        widened.json()["error"]["message"]
        == "a product policy cannot allow what the stock location does not"
    )
    for model in POLICY_TABLES:
        assert await stored(factory, tenant_a, model, item) == []

    accepted = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(godown, allow_sale_issue=False)]),
    )
    assert accepted.status_code == 200, accepted.text
    kept = await stored(factory, tenant_a, ItemWarehousePermission, item)
    assert [(row.allow_sale_issue, row.allow_purchase_receipt) for row in kept] == [(False, True)]


async def test_a_service_or_non_stock_product_is_never_stocked_at_a_location(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Both halves are checked because they disagree: a goods family may be typed
    NON_STOCK, and the read still answers with the baseline for either."""
    fixture = await provision(client, factory, tenant_a)
    company, current = fixture["company"], fixture["current"]
    main = fixture["config"]["main_warehouse_id"]
    service = await typed_item(
        factory, tenant_a, company, fixture["item"], kind="SERVICE", modes=["NON_STOCK"], code="SVC"
    )
    non_stock = await typed_item(
        factory, tenant_a, company, fixture["item"], kind="GOODS", modes=["NON_STOCK"], code="NST"
    )
    mixed_non_stock = await typed_item(
        factory,
        tenant_a,
        company,
        fixture["item"],
        kind="GOODS",
        modes=["STOCK", "NON_STOCK"],
        code="MIX",
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            mixed = await db.get(Item, uuid.UUID(mixed_non_stock))
            assert mixed is not None
            mixed.status = "ACTIVE"
    for target, message in (
        (service, "a service is never stocked at a location"),
        (non_stock, "a non-stock product is never stocked at a location"),
        (mixed_non_stock, "a non-stock product is never stocked at a location"),
    ):
        view = await read(client, policy_route(company, target), current)
        assert view["is_configured"] is False
        refused = await client.put(
            policy_route(company, target),
            headers=command_headers(current),
            json=policy_body(view, locations=[entry(main)]),
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["message"] == message
        bands = await client.put(
            band_route(company, target),
            headers=command_headers(current),
            json={"scopes": [], **guard(view)},
        )
        assert bands.status_code == 409, bands.text
        assert bands.json()["error"]["message"] == message
        for model in POLICY_TABLES:
            assert await stored(factory, tenant_a, model, target) == []


async def test_a_product_activity_default_must_serve_its_own_operation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A default that could not serve its operation would fail weeks later, on a document,
    with nothing recording why. It is refused where it is stated (§3)."""
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    transit = fixture["config"]["transit_warehouse_id"]
    godown = await location(client, company, current, "GD1")
    target = policy_route(company, item)
    view = await read(client, target, current)

    refused = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(
            view,
            locations=[entry(godown, allow_sale_issue=False)],
            default_sale_warehouse_id=godown,
        ),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["message"].endswith("does not allow this operation")

    # A default outside the membership is a client error: it would assert a permission in
    # one column and deny it in another.
    unnamed = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(godown)], default_opening_warehouse_id=transit),
    )
    assert unnamed.status_code == 422, unnamed.text
    # Internal transit custody is never selectable, in either location mode.
    custody = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(transit)], default_opening_warehouse_id=transit),
    )
    assert custody.status_code == 422, custody.text
    for model in POLICY_TABLES:
        assert await stored(factory, tenant_a, model, item) == []

    accepted = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(godown)], default_sale_warehouse_id=godown),
    )
    assert accepted.status_code == 200, accepted.text
    assert (await read(client, target, current))["default_sale_warehouse_id"] == godown


async def test_a_stocked_product_blocks_the_locations_retirement(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID,
    native_retirement,
) -> None:
    """The fence works both ways: an active membership refuses the retirement, and a
    stranded activity default says so in its own words rather than failing later (§5)."""
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    godown = await location(client, company, current, "GD1")
    target = policy_route(company, item)
    retire = f"/v1/companies/{company}/warehouses/{godown}/deactivate"
    view = await read(client, target, current)
    pointed = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(godown)], default_purchase_warehouse_id=godown),
    )
    assert pointed.status_code == 200, pointed.text

    blocked = await client.post(
        retire, headers=command_headers(current), json={"expected_version": 1}
    )
    assert blocked.status_code == 409, blocked.text
    assert (
        blocked.json()["error"]["message"]
        == "reassign the product activity default before retiring a location"
    )
    view = await read(client, target, current)
    kept = await client.put(
        target, headers=command_headers(current), json=policy_body(view, locations=[entry(godown)])
    )
    assert kept.status_code == 200, kept.text
    stocked = await client.post(
        retire, headers=command_headers(current), json={"expected_version": 1}
    )
    assert stocked.status_code == 409, stocked.text
    assert (
        stocked.json()["error"]["message"]
        == "restate the products stocked here before retiring a location"
    )

    # Dropping the location retires the membership; nothing is deleted, so the trail keeps
    # that this product was once stocked there.
    view = await read(client, target, current)
    released = await client.put(
        target, headers=command_headers(current), json=policy_body(view, mode="ALLOW_ALL_ACTIVE")
    )
    assert released.status_code == 200, released.text
    rows = await stored(factory, tenant_a, ItemWarehousePermission, item)
    # Two versions, not three: the middle restatement dropped the parent's default pointer and
    # left this row's flags exactly as they were, so it was not rewritten.
    assert [(row.is_active, row.row_version) for row in rows] == [(False, 2)]
    assert (await read(client, target, current))["locations"] == []
    # Catalog's half of the fence is clear now, so the refusal moves to the half Catalog does not
    # own: no release states this policy yet, and no consumer has cleared the retirement against
    # it. Both are asserted in full in test_policy_release_api; here they are what stands between
    # a restated product policy and the location actually going away.
    unreleased = await client.post(
        retire, headers=command_headers(current), json={"expected_version": 1}
    )
    assert unreleased.status_code == 409, unreleased.text
    assert unreleased.json()["error"]["message"].startswith("publish a stock-location policy")
    retired = await retire_location(client, factory, tenant_a, company, godown, current)
    assert retired.status_code == 200, retired.text
    retirement = [
        row
        for row in await emitted(factory, tenant_a)
        if row.event_type == "catalog.item_warehouse_permission.update"
    ]
    # One retirement, recorded as what it is. The version marker carries no value: audit
    # evidence keeps safe scalars and marks the rest as changed (docs/audit.md §5.2).
    assert [row.payload["changes"] for row in retirement] == [
        {"is_active": {"from": "true", "to": "false"}, "row_version": {"changed": True}}
    ]


async def test_replenishment_bands_are_stated_whole_and_land_on_the_unit_grid(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Quantities are exact and on the ordering unit's grid; a band the product cannot be
    stocked for is refused, and a scope left out is retired rather than left stale."""
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    binding, main = fixture["binding"], fixture["config"]["main_warehouse_id"]
    godown = await location(client, company, current, "GD1")
    elsewhere = await location(client, company, current, "GD2")
    target = band_route(company, item)

    view = await read(client, target, current)
    assert view["scopes"] == []
    empty = await client.put(
        target, headers=command_headers(current), json={"scopes": [], **guard(view)}
    )
    assert empty.status_code == 409, empty.text
    assert (
        empty.json()["error"]["message"]
        == "this product has no replenishment bands to state or retire"
    )

    policy = await client.put(
        policy_route(company, item),
        headers=command_headers(current),
        json=policy_body(
            await read(client, policy_route(company, item), current),
            locations=[entry(main), entry(godown)],
        ),
    )
    assert policy.status_code == 200, policy.text

    view = await read(client, target, current)
    body = {
        "scopes": [band(binding), band(binding, warehouse=godown, safety_quantity="4")],
        **guard(view),
    }
    receipt = command_headers(current)
    written = await client.put(target, headers=receipt, json=body)
    assert written.status_code == 200, written.text
    replay = await client.put(target, headers=receipt, json=body)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == written.json()

    rows = await stored(factory, tenant_a, ItemReplenishmentPolicy, item)
    assert len(rows) == 2
    wide = next(row for row in rows if row.warehouse_id is None)
    assert wide.scope_warehouse_id == ITEM_WIDE_SCOPE
    # Storage keeps quantities exact: a float here would drift against the same unit grid
    # these values were validated on (CLAUDE.md §6.1).
    assert isinstance(wide.safety_quantity, Decimal) and wide.safety_quantity == Decimal("2")
    assert isinstance(wide.order_multiple, Decimal) and wide.order_multiple == Decimal("10")
    assert wide.max_order_quantity == Decimal("100") and wide.lead_time_days == 7
    scopes = {
        scope["is_item_wide"]: scope for scope in (await read(client, target, current))["scopes"]
    }
    assert set(scopes) == {True, False}
    assert Decimal(scopes[True]["safety_quantity"]) == Decimal("2")
    assert Decimal(scopes[False]["safety_quantity"]) == Decimal("4")
    assert scopes[False]["warehouse_id"] == godown
    assert scopes[True]["warehouse_id"] is None
    assert scopes[True]["purchase_binding_id"] == binding

    view = await read(client, target, current)
    for scope, status, message in (
        (band(binding, safety_quantity="2.5"), 422, "quantity grid"),
        (band(binding, safety_quantity=2.5), 422, ""),
        (band(binding, order_multiple="7", max_order_quantity="12"), 422, ""),
        (band(str(uuid7())), 409, "the ordering unit has no current or scheduled revision here"),
        (
            band(binding, warehouse=elsewhere),
            409,
            "this product is not stocked at that location",
        ),
    ):
        refused = await client.put(
            target, headers=command_headers(current), json={"scopes": [scope], **guard(view)}
        )
        assert refused.status_code == status, (scope, refused.text)
        if message:
            assert message in refused.json()["error"]["message"]
    assert len(await stored(factory, tenant_a, ItemReplenishmentPolicy, item)) == 2

    dropped = await client.put(
        target,
        headers=command_headers(current),
        json={"scopes": [band(binding)], **guard(view)},
    )
    assert dropped.status_code == 200, dropped.text
    rows = await stored(factory, tenant_a, ItemReplenishmentPolicy, item)
    assert {row.warehouse_id is None: row.is_active for row in rows} == {True: True, False: False}
    assert [scope["is_item_wide"] for scope in (await read(client, target, current))["scopes"]] == [
        True
    ]


async def test_product_policy_routes_are_permissioned_company_scoped_and_closed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    user, main = fixture["user"], fixture["config"]["main_warehouse_id"]
    policy, bands = policy_route(company, item), band_route(company, item)
    view = await read(client, policy, current)
    proposal = policy_body(view, locations=[entry(main)])
    scopes = {"scopes": [band(fixture["binding"])], **guard(view)}

    for path, body in ((policy, proposal), (bands, scopes)):
        assert (await client.get(path)).status_code == 401
        assert (await client.put(path, json=body)).status_code == 401

    unpermitted = headers(company, tenant=tenant_a, user=user, permission="unit.read")
    reader = headers(company, tenant=tenant_a, user=user, permission=list(READER))
    # Right entity, no location rights: the policy read answers with location identities, so
    # a reader who may not see the company's locations cannot enumerate them through it.
    blinkered = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["item.read", "item_warehouse_policy.read", "item_warehouse_policy.manage"],
    )
    for path, body in ((policy, proposal), (bands, scopes)):
        assert (await client.get(path, headers=unpermitted)).status_code == 403
        assert (
            await client.put(path, headers=command_headers(unpermitted), json=body)
        ).status_code == 403
        assert (await client.get(path, headers=reader)).status_code == 200
        assert (
            await client.put(path, headers=command_headers(reader), json=body)
        ).status_code == 403
        assert (await client.get(path, headers=blinkered)).status_code == 403

    # Right permission, wrong company: the object is forbidden, not hidden.
    other = await provision(client, factory, tenant_a)
    foreign = other["current"]
    assert (
        await client.get(policy_route(other["company"], item), headers=foreign)
    ).status_code == 403
    assert (
        await client.put(
            policy_route(other["company"], item), headers=command_headers(foreign), json=proposal
        )
    ).status_code == 403
    assert (
        await client.get(band_route(other["company"], item), headers=foreign)
    ).status_code == 403
    # Another tenant is not told the product exists.
    alien = await auth(factory, tenant_b, company, uuid7(), permission=STOCK)
    assert (await client.get(policy, headers=alien)).status_code == 404
    assert (
        await client.get(policy_route(company, str(uuid7())), headers=current)
    ).status_code == 404

    assert (await client.get(policy, headers=current, params={"as_of": "x"})).status_code == 422
    assert (
        await client.put(policy, headers=command_headers(current), params={"x": "1"}, json=proposal)
    ).status_code == 422
    assert (await client.put(policy, headers=current, json=proposal)).status_code == 422
    for body in (
        {key: value for key, value in proposal.items() if key != "expected_generation"},
        {**proposal, "extra": None},
        {**proposal, "locations": [entry(main), entry(main)]},
        {**proposal, "locations": []},
        {**proposal, "locations": [{**entry(main), "allow_teleport": True}]},
        {**proposal, "locations": [{**entry(main), "allow_sale_issue": "true"}]},
        {**proposal, "selection_mode": "ALLOW_NONE"},
        {**proposal, "expected_generation": 0},
        {**proposal, "default_sale_warehouse_id": "MAIN"},
    ):
        response = await client.put(policy, headers=command_headers(current), json=body)
        assert response.status_code == 422, (body, response.text)
    absent = await client.put(
        policy,
        headers=command_headers(current),
        json=policy_body(view, locations=[entry(str(uuid7()))]),
    )
    assert absent.status_code == 404, absent.text
    stale = await client.put(
        policy,
        headers=command_headers(current),
        json={**proposal, "expected_generation": view["policy_generation"] + 1},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["message"].startswith("product location policy or Identity source")
    for model in POLICY_TABLES:
        assert await stored(factory, tenant_a, model, item) == []


async def test_product_location_policies_are_tenant_isolated(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """Two tenants, one query each: neither sees the other's membership or band. The HTTP
    side of this is the alien-tenant 404 above; this is the session filter itself."""
    owned: dict[uuid.UUID, uuid.UUID] = {}
    for tenant in (tenant_a, tenant_b):
        fixture = await provision(client, factory, tenant)
        company, item, current = fixture["company"], fixture["item"], fixture["current"]
        main = fixture["config"]["main_warehouse_id"]
        written = await client.put(
            policy_route(company, item),
            headers=command_headers(current),
            json=policy_body(
                await read(client, policy_route(company, item), current),
                locations=[entry(main)],
            ),
        )
        assert written.status_code == 200, written.text
        band_view = await read(client, band_route(company, item), current)
        reviewed = await client.put(
            band_route(company, item),
            headers=command_headers(current),
            json={"scopes": [band(fixture["binding"])], **guard(band_view)},
        )
        assert reviewed.status_code == 200, reviewed.text
        owned[tenant] = uuid.UUID(item)
    for tenant, other in ((tenant_a, tenant_b), (tenant_b, tenant_a)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in POLICY_TABLES:
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert {row.tenant_id for row in rows} == {tenant}
                    assert {row.item_id for row in rows} == {owned[tenant]}
                    assert (
                        await db.scalar(
                            select(func.count(model.id)).where(model.item_id == owned[other])
                        )
                        == 0
                    )


async def test_a_denied_field_stays_denied_in_these_projections_and_writes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A field deny is authorization, enforced server-side on the changed-field set
    (docs/field-permissions.md §6)."""
    fixture = await provision(client, factory, tenant_a)
    company, item, current = fixture["company"], fixture["item"], fixture["current"]
    user, main = fixture["user"], fixture["config"]["main_warehouse_id"]
    godown = await location(client, company, current, "GD1")
    target = policy_route(company, item)
    written = await client.put(
        target,
        headers=command_headers(current),
        json=policy_body(
            await read(client, target, current), locations=[entry(main), entry(godown)]
        ),
    )
    assert written.status_code == 200, written.text

    # A denied location identity omits the entry whole: its flags alone would still disclose
    # that the product is stocked somewhere this reader may not see.
    hidden = await auth(
        factory,
        tenant_a,
        company,
        user,
        permission=STOCK,
        version=4,
        extra=(denial(company, user, "catalog.item_warehouse_permission", "warehouse_id", "read"),),
    )
    view = await read(client, target, hidden)
    assert view["is_configured"] is True and view["locations"] == []

    # A denied *location* flag withholds the composition rather than reporting a partial
    # intersection, which would read as a denial the reviewer never stated.
    partial = await auth(
        factory,
        tenant_a,
        company,
        user,
        permission=STOCK,
        version=5,
        extra=(
            denial(
                company,
                user,
                "catalog.warehouse_operation_policy_revision",
                "allow_adjustment",
                "read",
            ),
        ),
    )
    view = await read(client, target, partial)
    assert len(view["locations"]) == 2
    assert all("effective_operations" not in detail for detail in view["locations"])
    assert all(detail["allow_adjustment"] is True for detail in view["locations"])

    unwritable = await auth(
        factory,
        tenant_a,
        company,
        user,
        permission=STOCK,
        version=6,
        extra=(denial(company, user, "catalog.item_warehouse_policy", "selection_mode", "write"),),
    )
    view = await read(client, target, unwritable)
    denied = await client.put(
        target, headers=command_headers(unwritable), json=policy_body(view, mode="ALLOW_ALL_ACTIVE")
    )
    assert denied.status_code == 403, denied.text
    rows = await stored(factory, tenant_a, ItemWarehousePolicy, item)
    assert [row.selection_mode for row in rows] == ["ALLOW_LIST"]
    kept = await stored(factory, tenant_a, ItemWarehousePermission, item)
    assert {row.is_active for row in kept} == {True}
