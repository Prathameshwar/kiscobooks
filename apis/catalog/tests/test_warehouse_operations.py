"""Operation-policy revisions, inheritance on create and the activity-defaults action.

docs/catalog-warehouses.md §2, §3 and §5 over HTTP. Three things carry the weight, and each
is asserted as a refusal rather than as a convenience:

* a published revision is never rewritten — a change is a new number, and the trail keeps
  what the superseded one allowed;
* an activity default may only point at a location allowed to serve *that* operation, so a
  document never discovers the misconfiguration weeks later;
* both hold server-side, on the changed-field set, for every actor.
"""

import uuid
from collections.abc import Sequence
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.warehouses import OPERATION_FLAGS
from catalog.events.audit_contract import AUDIT_EVENTS
from catalog.models import Outbox
from catalog.models.warehouses import WarehouseOperationPolicyRevision
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import MULTI, PERMISSIONS, auth

#: Writing a revision needs `warehouse.manage`; publishing one adds `warehouse.publish`.
PUBLISHER = (*PERMISSIONS, "warehouse.publish")
ALLOW_ALL: dict[str, bool] = dict.fromkeys(OPERATION_FLAGS, True)


def policy(**changes: bool) -> dict[str, bool]:
    """The whole eight-flag policy: a publish states all of them together (§2)."""
    return {**ALLOW_ALL, **changes}


def expectations(source: dict[str, Any]) -> dict[str, Any]:
    """What a publish echoes back, from a preview or from the view the reviewer read."""
    return {
        "expected_generation": source.get("expected_generation", source.get("policy_generation")),
        "expected_source_version": source.get(
            "expected_source_version", source.get("source_version")
        ),
    }


def denial(company: uuid.UUID, user: uuid.UUID, field: str, access: str) -> SnapshotRecord:
    """One Identity field policy denying this user a policy flag, tenant-wide."""
    source = next(row for row in all_facts(company, user) if row.kind == "field_policy")
    return SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.warehouse_operation_policy_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": field,
            "access": access,
            "condition": None,
        },
    )


def route(company: uuid.UUID, warehouse: str) -> str:
    return f"/v1/companies/{company}/warehouses/{warehouse}/operation-policy"


async def provision(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    features: Sequence[str] = MULTI,
    permission: Sequence[str] = PUBLISHER,
    extra: Sequence[SnapshotRecord] = (),
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """A company with its built-in locations and their provisioned policies."""
    company, user = uuid7(), uuid7()
    current = await auth(
        factory, tenant, company, user, features=features, permission=permission, extra=extra
    )
    created = await client.post(
        f"/v1/companies/{company}/warehouse-configuration/bootstrap",
        headers=command_headers(current),
        json={},
    )
    assert created.status_code == 201, created.text
    return company, user, current


async def configuration(
    client: httpx.AsyncClient, company: uuid.UUID, current: dict[str, str]
) -> dict[str, Any]:
    response = await client.get(f"/v1/companies/{company}/warehouse-configuration", headers=current)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def godown(
    client: httpx.AsyncClient, company: uuid.UUID, current: dict[str, str], code: str = "GD1"
) -> str:
    created = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(current),
        json={"code": code, "name": code.title(), "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def stored(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, warehouse: str
) -> list[WarehouseOperationPolicyRevision]:
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(WarehouseOperationPolicyRevision)
                    .where(WarehouseOperationPolicyRevision.warehouse_id == uuid.UUID(warehouse))
                    .order_by(WarehouseOperationPolicyRevision.revision)
                )
            )


async def emitted(factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID) -> list[Outbox]:
    """This tenant's policy events. ``tenant_id`` is stated because ``outbox`` is deliberately
    exempt from the session filter (the poller reads across tenants), so ``tenant_scope`` alone
    would collect every tenant's rows in a database more than one test has written to."""
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(Outbox)
                    .where(
                        Outbox.tenant_id == tenant,
                        Outbox.aggregate_type == "catalog.warehouse_operation_policy_revision",
                    )
                    .order_by(Outbox.id)
                )
            )


async def test_a_publish_supersedes_the_revision_in_force_and_keeps_the_trail(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current = await provision(client, factory, tenant_a)
    main = (await configuration(client, company, current))["main_warehouse_id"]
    target = route(company, main)
    before = (await client.get(target, headers=current)).json()
    assert before["warehouse_id"] == main and before["current"]["revision"] == 1
    # Main is provisioned permitting everything: the bootstrap points all four defaults at it.
    assert all(before["current"][flag] is True for flag in OPERATION_FLAGS)
    assert before["current"]["effective_to"] is None
    assert before["current"]["delivery_state"] == "PENDING"
    assert [entry["revision"] for entry in before["history"]] == [1]

    proposal = policy(allow_adjustment=False)
    preview = await client.post(target + "/preview", headers=current, json=proposal)
    assert preview.status_code == 200, preview.text
    assert preview.json()["revision"] == 2 and preview.json()["publishable"] is True
    assert preview.json()["changed"] == ["allow_adjustment"] and preview.json()["issues"] == []
    assert preview.json()["delivery_state"] == "PENDING"
    assert expectations(preview.json()) == expectations(before)
    # A preview allocates nothing: the number it quotes is still free afterwards.
    assert len(await stored(factory, tenant_a, main)) == 1

    receipt = command_headers(current)
    body = {**proposal, **expectations(preview.json())}
    published = await client.post(target + "/publish", headers=receipt, json=body)
    assert published.status_code == 201, published.text
    assert published.headers["Idempotency-Replayed"] == "false"
    assert published.headers["Cache-Control"] == "no-store"
    result = published.json()
    assert result["id"] != before["current"]["id"] and result["row_version"] == 1
    assert result["policy_generation"] == before["policy_generation"] + 1
    replay = await client.post(target + "/publish", headers=receipt, json=body)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == result

    after = (await client.get(target, headers=current)).json()
    assert after["current"]["id"] == result["id"] and after["current"]["revision"] == 2
    assert after["current"]["allow_adjustment"] is False
    assert after["current"]["allow_sale_issue"] is True
    assert [entry["revision"] for entry in after["history"]] == [2, 1]
    superseded = after["history"][1]
    # The published revision is untouched apart from the window its successor closed, and the
    # two windows meet: there is no interval in which nothing was in force.
    assert superseded["id"] == before["current"]["id"]
    assert superseded["allow_adjustment"] is True
    assert superseded["effective_to"] == after["current"]["effective_from"]
    rows = await stored(factory, tenant_a, main)
    assert [(row.revision, row.allow_adjustment) for row in rows] == [(1, True), (2, False)]

    events = await emitted(factory, tenant_a)
    # Two built-in policies, the new revision, and the update that closed its predecessor.
    assert [
        row.event_type.removeprefix("catalog.warehouse_operation_policy_revision.")
        for row in events
    ] == [
        "create",
        "create",
        "update",
        "create",
    ]
    assert {row.event_type for row in events} <= AUDIT_EVENTS
    closing = next(row for row in events if row.event_type.endswith(".update"))
    assert closing.payload["changes"]["effective_to"]["from"] is None
    assert closing.payload["changes"]["effective_to"]["to"].removesuffix("+00:00") == after[
        "current"
    ]["effective_from"].removesuffix("Z")
    creation = events[-1]
    # Audit evidence keeps safe scalars as strings; the flag itself is what a reader needs.
    assert creation.payload["changes"]["allow_adjustment"] == {"from": None, "to": "false"}
    assert creation.payload["changes"]["allow_sale_issue"] == {"from": None, "to": "true"}
    assert creation.payload["changes"]["revision"] == {"from": None, "to": "2"}
    assert creation.payload["company_id"] == str(company)
    assert creation.payload["category"] == "admin"


async def test_a_proposal_that_changes_nothing_writes_nothing(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """History records reviewed *changes*; a row that changed nothing lengthens the trail."""
    company, _, current = await provision(client, factory, tenant_a)
    main = (await configuration(client, company, current))["main_warehouse_id"]
    target = route(company, main)
    view = (await client.get(target, headers=current)).json()
    preview = await client.post(target + "/preview", headers=current, json=policy())
    assert preview.status_code == 200, preview.text
    assert preview.json()["revision"] == 1 and preview.json()["changed"] == []
    assert [issue["code"] for issue in preview.json()["issues"]] == ["NO_CHANGE"]
    # Advisory, not a refusal: the publish is accepted and answers with the revision in force.
    assert preview.json()["publishable"] is True
    published = await client.post(
        target + "/publish",
        headers=command_headers(current),
        json={**policy(), **expectations(preview.json())},
    )
    assert published.status_code == 201, published.text
    assert published.json()["id"] == view["current"]["id"]
    assert published.json()["policy_generation"] == view["policy_generation"]
    assert len(await stored(factory, tenant_a, main)) == 1
    assert len(await emitted(factory, tenant_a)) == 2


async def test_a_publish_against_a_stale_picture_is_refused(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current = await provision(client, factory, tenant_a)
    main = (await configuration(client, company, current))["main_warehouse_id"]
    target = route(company, main)
    view = (await client.get(target, headers=current)).json()
    accepted = await client.post(
        target + "/publish",
        headers=command_headers(current),
        json={**policy(allow_adjustment=False), **expectations(view)},
    )
    assert accepted.status_code == 201, accepted.text
    now = (await client.get(target, headers=current)).json()
    assert now["policy_generation"] == view["policy_generation"] + 1
    for changes in (
        # The picture the reviewer read before the accepted publish, a generation that does
        # not exist yet, and an Identity checkpoint Catalog has never seen.
        expectations(view),
        {**expectations(now), "expected_generation": now["policy_generation"] + 1},
        {**expectations(now), "expected_source_version": now["source_version"] + 1},
    ):
        refused = await client.post(
            target + "/publish",
            headers=command_headers(current),
            json={**policy(allow_opening_stock=False), **changes},
        )
        assert refused.status_code == 409, (changes, refused.text)
        assert refused.json()["error"]["message"].startswith("location policy or Identity source")
    assert len(await stored(factory, tenant_a, main)) == 2


async def test_internal_transit_custody_has_a_reserved_policy(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current = await provision(client, factory, tenant_a)
    transit = (await configuration(client, company, current))["transit_warehouse_id"]
    target = route(company, transit)
    view = (await client.get(target, headers=current)).json()
    # Custody is only ever a transfer leg; resolution refuses to select it at all.
    assert view["current"]["allow_transfer_in"] is True
    assert view["current"]["allow_transfer_out"] is True
    assert view["current"]["allow_sale_issue"] is False
    assert view["current"]["allow_opening_stock"] is False
    preview = await client.post(target + "/preview", headers=current, json=policy())
    assert preview.status_code == 200, preview.text
    assert preview.json()["publishable"] is False
    assert [issue["code"] for issue in preview.json()["issues"]] == ["RESERVED_LOCATION"]
    refused = await client.post(
        target + "/publish",
        headers=command_headers(current),
        json={**policy(), **expectations(view)},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["message"].startswith("internal transit custody")
    assert len(await stored(factory, tenant_a, transit)) == 1


async def test_a_new_location_inherits_the_reviewed_policy_without_publish_rights(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A location that allowed everything because somebody named it would infer permissions
    from a name (§2). It starts as Main's reviewed answer, and diverges from then on."""
    company, user, current = await provision(client, factory, tenant_a)
    main = (await configuration(client, company, current))["main_warehouse_id"]
    view = (await client.get(route(company, main), headers=current)).json()
    reviewed = await client.post(
        route(company, main) + "/publish",
        headers=command_headers(current),
        json={**policy(allow_adjustment=False), **expectations(view)},
    )
    assert reviewed.status_code == 201, reviewed.text

    manager = headers(company, tenant=tenant_a, user=user, permission=list(PERMISSIONS))
    receipt = command_headers(manager)
    created = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=receipt,
        json={"code": "GD1", "name": "North godown", "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    location = str(created.json()["id"])
    inherited = (await client.get(route(company, location), headers=manager)).json()
    assert inherited["current"]["revision"] == 1
    assert inherited["current"]["allow_adjustment"] is False
    assert inherited["current"]["allow_sale_issue"] is True
    assert inherited["current"]["effective_to"] is None
    # A retained create receipt is re-authorized, not re-applied.
    replay = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=receipt,
        json={"code": "GD1", "name": "North godown", "kind": "GODOWN"},
    )
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert len(await stored(factory, tenant_a, location)) == 1
    # The location diverges from its template: Main is not rewritten by the inheritance.
    assert len(await stored(factory, tenant_a, main)) == 2


async def test_activity_defaults_only_reach_locations_allowed_to_serve_them(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, current = await provision(client, factory, tenant_a)
    config = await configuration(client, company, current)
    main, transit = config["main_warehouse_id"], config["transit_warehouse_id"]
    location = await godown(client, company, current)
    view = (await client.get(route(company, location), headers=current)).json()
    narrowed = await client.post(
        route(company, location) + "/publish",
        headers=command_headers(current),
        json={**policy(allow_sale_issue=False), **expectations(view)},
    )
    assert narrowed.status_code == 201, narrowed.text
    defaults = f"/v1/companies/{company}/warehouse-configuration/defaults"
    config = await configuration(client, company, current)
    pointers = {
        "default_sale_warehouse_id": main,
        "default_purchase_warehouse_id": main,
        "default_customer_return_warehouse_id": main,
        "default_opening_warehouse_id": main,
    }
    refused = await client.post(
        defaults,
        headers=command_headers(current),
        json={
            **pointers,
            "default_sale_warehouse_id": location,
            **expectations(config),
        },
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["message"].endswith("does not allow this operation")
    # Transit is custody, never a default, in any mode.
    assert (
        await client.post(
            defaults,
            headers=command_headers(current),
            json={**pointers, "default_opening_warehouse_id": transit, **expectations(config)},
        )
    ).status_code == 422
    assert (await configuration(client, company, current))["row_version"] == config["row_version"]

    accepted = await client.post(
        defaults,
        headers=command_headers(current),
        json={
            **pointers,
            "default_purchase_warehouse_id": location,
            "default_customer_return_warehouse_id": None,
            **expectations(config),
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.headers["Idempotency-Replayed"] == "false"
    moved = await configuration(client, company, current)
    assert moved["default_purchase_warehouse_id"] == location
    assert moved["default_sale_warehouse_id"] == main
    # `null` is a real value: no default configured, and resolution then reaches Main.
    assert moved["default_customer_return_warehouse_id"] is None
    assert moved["row_version"] == config["row_version"] + 1
    # Repointing a default moves no stock and rewrites no policy.
    assert [row.revision for row in await stored(factory, tenant_a, location)] == [1, 2]
    assert [row.revision for row in await stored(factory, tenant_a, main)] == [1]
    with tenant_scope(tenant_a):
        async with factory() as db:
            updates = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.tenant_id == tenant_a,
                        Outbox.event_type == "catalog.company_warehouse_configuration.update",
                    )
                )
            )
    assert len(updates) == 1
    changes = updates[0].payload["changes"]
    assert changes["default_purchase_warehouse_id"] == {"from": main, "to": location}
    assert changes["default_customer_return_warehouse_id"] == {"from": main, "to": None}


async def test_a_single_location_company_may_only_default_to_main(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Losing `multi_godown` does not rewrite a stored pointer to Main; it refuses the write."""
    company, user, current = await provision(client, factory, tenant_a)
    main = (await configuration(client, company, current))["main_warehouse_id"]
    location = await godown(client, company, current)
    # Creating a location is itself a reviewed change, so the expectations are read after it.
    config = await configuration(client, company, current)
    defaults = f"/v1/companies/{company}/warehouse-configuration/defaults"
    pointers = {
        "default_sale_warehouse_id": location,
        "default_purchase_warehouse_id": main,
        "default_customer_return_warehouse_id": main,
        "default_opening_warehouse_id": main,
    }
    accepted = await client.post(
        defaults, headers=command_headers(current), json={**pointers, **expectations(config)}
    )
    assert accepted.status_code == 200, accepted.text
    single = await auth(
        factory,
        tenant_a,
        company,
        user,
        features=("inventory",),
        permission=PUBLISHER,
        version=3,
    )
    config = await configuration(client, company, single)
    assert config["location_mode"] == "SINGLE_LOCATION"
    refused = await client.post(
        defaults, headers=command_headers(single), json={**pointers, **expectations(config)}
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "feature_not_enabled"
    assert refused.json()["error"]["feature"] == "multi_godown"
    assert (await configuration(client, company, single))["default_sale_warehouse_id"] == location
    at_main = await client.post(
        defaults,
        headers=command_headers(single),
        json={**pointers, "default_sale_warehouse_id": main, **expectations(config)},
    )
    assert at_main.status_code == 200, at_main.text
    assert (await configuration(client, company, single))["default_sale_warehouse_id"] == main


async def test_policy_routes_are_permissioned_company_scoped_and_closed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user, current = await provision(client, factory, tenant_a)
    config = await configuration(client, company, current)
    main = config["main_warehouse_id"]
    target = route(company, main)
    defaults = f"/v1/companies/{company}/warehouse-configuration/defaults"
    pointers = dict.fromkeys(
        (
            "default_sale_warehouse_id",
            "default_purchase_warehouse_id",
            "default_customer_return_warehouse_id",
            "default_opening_warehouse_id",
        ),
        main,
    )
    proposal = {**policy(allow_adjustment=False), **expectations(config)}

    assert (await client.get(target)).status_code == 401
    assert (await client.post(target + "/preview", json=policy())).status_code == 401
    assert (await client.post(target + "/publish", json=proposal)).status_code == 401
    assert (
        await client.post(defaults, json={**pointers, **expectations(config)})
    ).status_code == 401

    unpermitted = headers(company, tenant=tenant_a, user=user, permission="item.read")
    assert (await client.get(target, headers=unpermitted)).status_code == 403
    assert (
        await client.post(target + "/preview", headers=unpermitted, json=policy())
    ).status_code == 403
    assert (
        await client.post(target + "/publish", headers=command_headers(unpermitted), json=proposal)
    ).status_code == 403
    # Reading is enough to preview; publishing is a separate grant.
    reader = headers(company, tenant=tenant_a, user=user, permission="warehouse.read")
    assert (
        await client.post(target + "/preview", headers=reader, json=policy())
    ).status_code == 200
    manager = headers(company, tenant=tenant_a, user=user, permission=list(PERMISSIONS))
    assert (
        await client.post(target + "/publish", headers=command_headers(manager), json=proposal)
    ).status_code == 403
    assert (
        await client.post(
            defaults,
            headers=command_headers(manager),
            json={**pointers, **expectations(config)},
        )
    ).status_code == 403

    # Right permission, wrong company: the object is forbidden, not hidden.
    other, _, foreign = await provision(client, factory, tenant_a)
    assert (await client.get(route(other, main), headers=foreign)).status_code == 403
    assert (
        await client.post(route(other, main) + "/preview", headers=foreign, json=policy())
    ).status_code == 403
    assert (
        await client.post(
            route(other, main) + "/publish", headers=command_headers(foreign), json=proposal
        )
    ).status_code == 403
    assert (await client.get(target, headers=foreign)).status_code == 403
    # Another tenant is not told the row exists.
    alien = await auth(factory, tenant_b, company, uuid7(), permission=PUBLISHER)
    assert (await client.get(target, headers=alien)).status_code == 404
    assert (await client.get(route(company, str(uuid7())), headers=current)).status_code == 404

    assert (
        await client.get(target, headers=current, params={"as_of": "2026-01-01"})
    ).status_code == 422
    assert (
        await client.post(target + "/publish", headers=current, json=proposal)
    ).status_code == 422
    for body in (
        {flag: True for flag in OPERATION_FLAGS if flag != "allow_adjustment"},
        {**policy(), "allow_extra": True},
        {**policy(), "allow_adjustment": "true"},
        policy(),
        {**proposal, "expected_generation": 0},
    ):
        response = await client.post(
            target + "/publish", headers=command_headers(current), json=body
        )
        assert response.status_code == 422, (body, response.text)
    for body in (
        {**pointers, **expectations(config), "default_sale_warehouse_id": "MAIN"},
        {key: value for key, value in pointers.items() if key != "default_opening_warehouse_id"}
        | expectations(config),
        {**pointers, **expectations(config), "extra": None},
    ):
        response = await client.post(defaults, headers=command_headers(current), json=body)
        assert response.status_code == 422, (body, response.text)
    absent = await client.post(
        defaults,
        headers=command_headers(current),
        json={**pointers, "default_sale_warehouse_id": str(uuid7()), **expectations(config)},
    )
    assert absent.status_code == 404, absent.text


async def test_operation_policies_are_tenant_isolated(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """One company identifier, two tenants: neither sees the other's policy history."""
    company = uuid7()
    owned: dict[uuid.UUID, str] = {}
    for tenant in (tenant_a, tenant_b):
        current = await auth(factory, tenant, company, uuid7(), permission=PUBLISHER)
        created = await client.post(
            f"/v1/companies/{company}/warehouse-configuration/bootstrap",
            headers=command_headers(current),
            json={},
        )
        assert created.status_code == 201, created.text
        config = await configuration(client, company, current)
        owned[tenant] = config["main_warehouse_id"]
        if tenant == tenant_a:
            view = (await client.get(route(company, owned[tenant]), headers=current)).json()
            published = await client.post(
                route(company, owned[tenant]) + "/publish",
                headers=command_headers(current),
                json={**policy(allow_adjustment=False), **expectations(view)},
            )
            assert published.status_code == 201, published.text
    assert owned[tenant_a] != owned[tenant_b]
    for tenant, count in ((tenant_a, 3), (tenant_b, 2)):
        with tenant_scope(tenant):
            async with factory() as db:
                rows = list(await db.scalars(select(WarehouseOperationPolicyRevision)))
                assert len(rows) == count
                assert {row.tenant_id for row in rows} == {tenant}
                assert {row.company_id for row in rows} == {company}
                assert (
                    await db.scalar(
                        select(func.count(WarehouseOperationPolicyRevision.id)).where(
                            WarehouseOperationPolicyRevision.warehouse_id
                            == uuid.UUID(owned[tenant_b if tenant == tenant_a else tenant_a])
                        )
                    )
                    == 0
                )


async def test_a_denied_policy_flag_stays_denied_in_projections_and_writes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A field deny is authorization, enforced server-side (docs/field-permissions.md §6)."""
    company, user, current = await provision(client, factory, tenant_a)
    main = (await configuration(client, company, current))["main_warehouse_id"]
    target = route(company, main)
    hidden = await auth(
        factory,
        tenant_a,
        company,
        user,
        permission=PUBLISHER,
        version=3,
        extra=(denial(company, user, "allow_adjustment", "read"),),
    )
    view = await client.get(target, headers=hidden)
    assert view.status_code == 200, view.text
    assert "allow_adjustment" not in view.json()["current"]
    assert view.json()["current"]["allow_sale_issue"] is True
    assert "allow_adjustment" not in view.json()["history"][0]
    # A diff discloses the current value, so a denied flag is absent from it.
    preview = await client.post(
        target + "/preview", headers=hidden, json=policy(allow_adjustment=False)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["changed"] == [] and preview.json()["issues"] == []
    assert preview.json()["revision"] == 2
    # Publishing a policy whose current state is partly unreadable is refused outright.
    refused = await client.post(
        target + "/publish",
        headers=command_headers(hidden),
        json={**policy(allow_adjustment=False), **expectations(preview.json())},
    )
    assert refused.status_code == 403, refused.text
    assert len(await stored(factory, tenant_a, main)) == 1

    unwritable = await auth(
        factory,
        tenant_a,
        company,
        user,
        permission=PUBLISHER,
        version=4,
        extra=(denial(company, user, "allow_adjustment", "write"),),
    )
    view = await client.get(target, headers=unwritable)
    assert view.status_code == 200 and view.json()["current"]["allow_adjustment"] is True
    denied = await client.post(
        target + "/publish",
        headers=command_headers(unwritable),
        json={**policy(allow_adjustment=False), **expectations(view.json())},
    )
    assert denied.status_code == 403, denied.text
    assert len(await stored(factory, tenant_a, main)) == 1
    assert len(await emitted(factory, tenant_a)) == 2
