"""Location definitions over HTTP: provisioning, feature modes and the reserved rows."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.reference_models import State
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.warehouses import CompanyWarehouseConfiguration, Warehouse
from tests.commercial_factories import reference_data
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import RETIRE, auth, retire


async def test_bootstrap_provisions_one_built_in_set_and_replays(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouse-configuration"
    assert (await client.get(route, headers=current)).status_code == 404
    receipt = command_headers(current)
    created = await client.post(route + "/bootstrap", headers=receipt, json={})
    assert created.status_code == 201, created.text
    assert created.headers["Idempotency-Replayed"] == "false"
    assert created.headers["Cache-Control"] == "no-store"
    replay = await client.post(route + "/bootstrap", headers=receipt, json={})
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == created.json()
    # A fresh key runs the handler again; provisioning is idempotent by state, not only by key.
    again = await client.post(route + "/bootstrap", headers=command_headers(current), json={})
    assert again.status_code == 201 and again.json()["id"] == created.json()["id"]
    detail = await client.get(route, headers=current)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["location_mode"] == "MULTI_LOCATION"
    assert body["main_warehouse_id"] != body["transit_warehouse_id"]
    assert body["default_sale_warehouse_id"] == body["main_warehouse_id"]
    assert body["default_purchase_warehouse_id"] == body["main_warehouse_id"]
    assert body["default_customer_return_warehouse_id"] == body["main_warehouse_id"]
    assert body["default_opening_warehouse_id"] == body["main_warehouse_id"]
    # `source_version` is the live Identity checkpoint a defaults change must echo back;
    # `provisioned_source_version` is the picture the built-in set was derived from. They
    # agree here and part company the moment Identity advances.
    assert body["source_version"] == 2 and body["provisioned_source_version"] == 2
    assert body["row_version"] == 1
    listed = await client.get(f"/v1/companies/{company}/warehouses", headers=current)
    assert listed.status_code == 200
    assert [(row["code"], row["kind"], row["is_system"]) for row in listed.json()["items"]] == [
        ("MAIN", "STORE", True),
        ("TRANSIT", "INTERNAL_TRANSIT", True),
    ]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Warehouse.id))) == 2
            main = await db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
            transit = await db.scalar(select(Warehouse).where(Warehouse.code == "TRANSIT"))
            # Catalog copies the company timezone it already holds and invents no address.
            assert main is not None and main.timezone == "Asia/Kolkata"
            assert main.city is None and main.country_code is None
            assert transit is not None and transit.timezone is None


async def test_bootstrap_body_and_query_surface_is_closed(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouse-configuration/bootstrap"
    assert (await client.post(route, json={})).status_code == 401
    reader = headers(company, tenant=tenant_a, user=user, permission="warehouse.read")
    assert (await client.post(route, headers=command_headers(reader), json={})).status_code == 403
    assert (
        await client.post(
            route, headers=command_headers(current), json={"main_warehouse_id": str(uuid7())}
        )
    ).status_code == 422
    assert (await client.post(route, headers=command_headers(current))).status_code == 422
    assert (
        await client.post(
            route, headers=command_headers(current), json={}, params={"force": "true"}
        )
    ).status_code == 422


async def test_client_location_create_catches_up_provisioning_and_guards_reserved_rows(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    await reference_data(factory)
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouses"
    created = await client.post(
        route,
        headers=command_headers(current),
        json={
            "code": "GD1",
            "name": "North godown",
            "kind": "GODOWN",
            "city": "Pune",
            "country_code": "IN",
            "state_code": "IN-MH",
            "timezone": "Asia/Kolkata",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_system"] is False and created.json()["kind"] == "GODOWN"
    assert created.json()["state_code"] == "IN-MH"
    # The built-in set exists even though no bootstrap call was made.
    configuration = await client.get(
        f"/v1/companies/{company}/warehouse-configuration", headers=current
    )
    assert configuration.status_code == 200
    assert configuration.json()["main_warehouse_id"] != created.json()["id"]
    for body, status in (
        ({"code": "MAIN", "name": "Impostor", "kind": "STORE"}, 422),
        ({"code": "TRANSIT", "name": "Impostor", "kind": "STORE"}, 422),
        ({"code": "GD2", "name": "Custody", "kind": "INTERNAL_TRANSIT"}, 422),
        ({"code": "GD2", "name": "Nowhere", "kind": "GODOWN", "state_code": "IN-MH"}, 422),
        ({"code": "GD2", "name": " ", "kind": "GODOWN"}, 422),
        ({"code": "gd2", "name": "Lowercase", "kind": "GODOWN"}, 422),
        # A syntactically valid ISO code that names nothing, and a state that belongs to a
        # different country, are both refused by the application: on MySQL the two foreign
        # keys do not cover the first case (tasks/reference_locations.py).
        ({"code": "GD2", "name": "Unknown", "kind": "GODOWN", "country_code": "ZZ"}, 422),
        (
            {
                "code": "GD2",
                "name": "Elsewhere",
                "kind": "GODOWN",
                "country_code": "IN",
                "state_code": "US-CA",
            },
            422,
        ),
        ({"code": "GD1", "name": "Duplicate", "kind": "GODOWN"}, 409),
    ):
        response = await client.post(route, headers=command_headers(current), json=body)
        assert response.status_code == status, (body, response.text)


async def test_a_location_names_an_active_place_on_every_write_that_selects_one(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    native_retirement,
) -> None:
    """The application answers for the ISO pair, because on MySQL the two foreign keys do not.

    With ``state_code`` NULL, InnoDB accepts an unknown ``country_code`` even though the
    single-column constraint is declared and recorded; SQLite refuses it, so a schema-only
    check reads as green here and is absent in production (tasks/reference_locations.py).
    """
    company, user = uuid7(), uuid7()
    await reference_data(factory)
    current = await auth(factory, tenant_a, company, user, permission=RETIRE)
    route = f"/v1/companies/{company}/warehouses"
    created = await client.post(
        route,
        headers=command_headers(current),
        json={
            "code": "GD1",
            "name": "North godown",
            "kind": "GODOWN",
            "country_code": "IN",
            "state_code": "IN-MH",
        },
    )
    assert created.status_code == 201, created.text
    godown = created.json()["id"]
    for changes, message in (
        ({"country_code": "ZZ"}, "location country must be active"),
        ({"state_code": "US-CA"}, "location state must be active in the selected country"),
    ):
        refused = await client.patch(
            f"{route}/{godown}",
            headers=command_headers(current),
            json={"expected_version": 1, **changes},
        )
        assert refused.status_code == 422, (changes, refused.text)
        assert refused.json()["error"]["message"] == message, (changes, refused.text)
    # A code withdrawn from ISO is deactivated, never deleted (CLAUDE.md invariant 12), so it
    # stays on rows that already named it. That must not freeze them: an edit naming no
    # reference goes through, and only a write that re-selects the pair is held to it.
    async with factory.begin() as db:
        state = await db.get(State, "IN-MH")
        assert state is not None
        state.is_active = False
    renamed = await client.patch(
        f"{route}/{godown}",
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Renamed godown"},
    )
    assert renamed.status_code == 200, renamed.text
    retired = await retire(client, factory, tenant_a, company, godown, current, expected_version=2)
    assert retired.status_code == 200, retired.text
    reactivated = await client.post(
        f"{route}/{godown}/activate",
        headers=command_headers(current),
        json={"expected_version": 3},
    )
    assert reactivated.status_code == 422, reactivated.text
    assert reactivated.json()["error"]["message"].startswith("location state")
    # Clearing the withdrawn subdivision is the way back: the country it named is still current.
    cleared = await client.patch(
        f"{route}/{godown}",
        headers=command_headers(current),
        json={"expected_version": 3, "state_code": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert (
        await client.post(
            f"{route}/{godown}/activate",
            headers=command_headers(current),
            json={"expected_version": 4},
        )
    ).status_code == 200


async def test_main_accepts_location_facts_but_never_an_identity_or_lifecycle_change(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    await reference_data(factory)
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouse-configuration"
    assert (
        await client.post(route + "/bootstrap", headers=command_headers(current), json={})
    ).status_code == 201
    configuration = (await client.get(route, headers=current)).json()
    main = f"/v1/companies/{company}/warehouses/{configuration['main_warehouse_id']}"
    renamed = await client.patch(
        main, headers=command_headers(current), json={"expected_version": 1, "name": "Head store"}
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Head store", renamed.text
    # Main is a real place: the company fills its address in, exactly like any other store.
    located = await client.patch(
        main,
        headers=command_headers(current),
        json={
            "expected_version": 2,
            "city": "Pune",
            "country_code": "IN",
            "state_code": "IN-MH",
            "postal_code": "411001",
        },
    )
    assert located.status_code == 200 and located.json()["city"] == "Pune", located.text
    # `kind` and `is_system` are not on the update surface at all; `code` reaches the rule.
    for changes, status in (
        ({"kind": "GODOWN"}, 422),
        ({"is_system": False}, 422),
        ({"code": "HQ"}, 409),
    ):
        response = await client.patch(
            main, headers=command_headers(current), json={"expected_version": 3, **changes}
        )
        assert response.status_code == status, (changes, response.text)
    retired = await client.post(
        main + "/deactivate", headers=command_headers(current), json={"expected_version": 3}
    )
    assert retired.status_code == 409, retired.text
    assert retired.json()["error"]["message"].startswith("the built-in location's identity")
    # Activating a row that is already active changes nothing, so no rule is reached.
    unchanged = await client.post(
        main + "/activate", headers=command_headers(current), json={"expected_version": 3}
    )
    assert unchanged.status_code == 200 and unchanged.json()["row_version"] == 3, unchanged.text


async def test_internal_transit_records_no_physical_location_facts(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    await reference_data(factory)
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouse-configuration"
    assert (
        await client.post(route + "/bootstrap", headers=command_headers(current), json={})
    ).status_code == 201
    configuration = (await client.get(route, headers=current)).json()
    transit = f"/v1/companies/{company}/warehouses/{configuration['transit_warehouse_id']}"
    renamed = await client.patch(
        transit,
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Transit custody"},
    )
    assert renamed.status_code == 200, renamed.text
    for changes in (
        {"country_code": "IN"},
        {"timezone": "Asia/Kolkata"},
        {"city": "Pune"},
        {"department_id": str(uuid7())},
    ):
        response = await client.patch(
            transit, headers=command_headers(current), json={"expected_version": 2, **changes}
        )
        assert response.status_code == 409, (changes, response.text)
        assert response.json()["error"]["message"].startswith("internal transit custody")
    retired = await client.post(
        transit + "/deactivate", headers=command_headers(current), json={"expected_version": 2}
    )
    assert retired.status_code == 409, retired.text
    unchanged = await client.post(
        transit + "/activate", headers=command_headers(current), json={"expected_version": 2}
    )
    assert unchanged.status_code == 200 and unchanged.json()["row_version"] == 2, unchanged.text


@pytest.mark.parametrize(
    ("features", "mode", "feature"),
    [
        ((), "METADATA_ONLY", "inventory"),
        (("inventory",), "SINGLE_LOCATION", "multi_godown"),
    ],
)
async def test_additional_locations_are_refused_without_the_feature(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    features: tuple[str, ...],
    mode: str,
    feature: str,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, features=features)
    refused = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(current),
        json={"code": "GD1", "name": "Godown", "kind": "GODOWN"},
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()["error"]
    assert body["code"] == "feature_not_enabled" and body["feature"] == feature
    # The refusal is the point: nothing was remapped to Main, and nothing was provisioned.
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Warehouse.id))) == 0
            assert await db.scalar(select(func.count(CompanyWarehouseConfiguration.id))) == 0
    # The built-in set itself is always available: Main is where a metadata-only company posts.
    assert (
        await client.post(
            f"/v1/companies/{company}/warehouse-configuration/bootstrap",
            headers=command_headers(current),
            json={},
        )
    ).status_code == 201
    detail = await client.get(f"/v1/companies/{company}/warehouse-configuration", headers=current)
    assert detail.status_code == 200 and detail.json()["location_mode"] == mode


async def test_retired_location_cannot_return_once_the_feature_is_gone(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    native_retirement,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=RETIRE)
    route = f"/v1/companies/{company}/warehouses"
    created = await client.post(
        route,
        headers=command_headers(current),
        json={"code": "GD1", "name": "Godown", "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    identity = str(created.json()["id"])
    target = route + "/" + identity
    # Retirement needs both halves of the fence: a published release, and Billing's clearance
    # against it. The ladder each of those refusals forms is asserted in test_policy_release_api.
    retired = await retire(client, factory, tenant_a, company, identity, current)
    assert retired.status_code == 200, retired.text
    # The company loses multi_godown; the retired location may not come back.
    narrowed = await auth(
        factory, tenant_a, company, user, features=("inventory",), permission=RETIRE, version=3
    )
    refused = await client.post(
        target + "/activate", headers=command_headers(narrowed), json={"expected_version": 2}
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["feature"] == "multi_godown"
    restored = await auth(factory, tenant_a, company, user, version=4)
    assert (
        await client.post(
            target + "/activate", headers=command_headers(restored), json={"expected_version": 2}
        )
    ).status_code == 200


async def test_location_reads_are_company_and_tenant_scoped(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    own, other, user = uuid7(), uuid7(), uuid7()
    current = await auth(factory, tenant_a, own, user)
    foreign = await auth(factory, tenant_a, other, uuid7())
    created = await client.post(
        f"/v1/companies/{own}/warehouses",
        headers=command_headers(current),
        json={"code": "GD1", "name": "Godown", "kind": "GODOWN"},
    )
    assert created.status_code == 201, created.text
    identity = created.json()["id"]
    # Right permission, wrong company: within the tenant the object is forbidden, not hidden.
    assert (
        await client.get(f"/v1/companies/{other}/warehouses/{identity}", headers=foreign)
    ).status_code == 403
    # Right object, but the actor holds no grant on the owning company.
    assert (
        await client.get(f"/v1/companies/{own}/warehouses/{identity}", headers=foreign)
    ).status_code == 403
    assert (await client.get(f"/v1/companies/{other}/warehouses", headers=foreign)).json()[
        "items"
    ] == []
    # Another tenant sees nothing at all, not even that the row exists.
    alien = await auth(factory, tenant_b, own, uuid7())
    assert (
        await client.get(f"/v1/companies/{own}/warehouses/{identity}", headers=alien)
    ).status_code == 404
    assert (
        await client.get(f"/v1/companies/{own}/warehouse-configuration", headers=alien)
    ).status_code == 404
    assert (await client.get(f"/v1/companies/{own}/warehouses/{identity}")).status_code == 401
    assert (await client.get(f"/v1/companies/{own}/warehouses")).status_code == 401
    unpermitted = headers(own, tenant=tenant_a, user=user, permission="item.read")
    for path in (f"/warehouses/{identity}", "/warehouses", "/warehouse-configuration"):
        response = await client.get(f"/v1/companies/{own}" + path, headers=unpermitted)
        assert response.status_code == 403, (path, response.text)
    assert (
        await client.get(f"/v1/companies/{own}/warehouses/{uuid7()}", headers=current)
    ).status_code == 404


async def test_location_writes_require_manage_and_an_idempotency_key(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouses"
    body = {"code": "GD1", "name": "Godown", "kind": "GODOWN"}
    assert (await client.post(route, json=body)).status_code == 401
    assert (await client.post(route, headers=current, json=body)).status_code == 422
    reader = headers(company, tenant=tenant_a, user=user, permission="warehouse.read")
    assert (await client.post(route, headers=command_headers(reader), json=body)).status_code == 403
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=body)
    assert created.status_code == 201, created.text
    replay = await client.post(route, headers=receipt, json=body)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == created.json()
    target = route + "/" + created.json()["id"]
    assert (
        await client.patch(
            target, headers=command_headers(reader), json={"expected_version": 1, "name": "Other"}
        )
    ).status_code == 403
    assert (
        await client.patch(
            target, headers=command_headers(current), json={"expected_version": 9, "name": "Other"}
        )
    ).status_code == 409
    assert (
        await client.patch(target, headers=command_headers(current), json={"name": "Other"})
    ).status_code == 422
    assert (
        await client.patch(
            target,
            headers=command_headers(current),
            json={"expected_version": 1, "kind": "STORE"},
        )
    ).status_code == 422
    assert (
        await client.patch(
            target, headers=command_headers(current), json={"expected_version": 1, "name": None}
        )
    ).status_code == 422


async def test_location_list_filters_search_and_sort(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouses"
    for code, name, kind in (("GD1", "North godown", "GODOWN"), ("ST1", "South store", "STORE")):
        response = await client.post(
            route, headers=command_headers(current), json={"code": code, "name": name, "kind": kind}
        )
        assert response.status_code == 201, response.text
    assert [row["code"] for row in (await client.get(route, headers=current)).json()["items"]] == [
        "GD1",
        "MAIN",
        "ST1",
        "TRANSIT",
    ]
    assert [
        row["code"]
        for row in (await client.get(route, headers=current, params={"kind": "GODOWN"})).json()[
            "items"
        ]
    ] == ["GD1"]
    assert [
        row["code"]
        for row in (
            await client.get(route, headers=current, params={"is_system": "true", "sort": "-code"})
        ).json()["items"]
    ] == ["TRANSIT", "MAIN"]
    assert [
        row["code"]
        for row in (
            await client.get(route, headers=current, params={"kind": "INTERNAL_TRANSIT"})
        ).json()["items"]
    ] == ["TRANSIT"]
    assert [
        row["code"]
        for row in (await client.get(route, headers=current, params={"q": "South"})).json()["items"]
    ] == ["ST1"]
    first = await client.get(route, headers=current, params={"limit": 1, "sort": "code"})
    assert first.json()["items"][0]["code"] == "GD1"
    following = await client.get(
        route,
        headers=current,
        params={"limit": 1, "sort": "code", "cursor": first.json()["page"]["next_cursor"]},
    )
    assert following.json()["items"][0]["code"] == "MAIN"
    for params in (
        {"kind": "STOREROOM"},
        {"sort": "city"},
        {"limit": 201},
        {"is_system": "maybe"},
        {"code": "GD1", "code_extra": "x"},
    ):
        response = await client.get(route, headers=current, params=params)
        assert response.status_code == 422, (params, response.text)


async def test_warehouse_tax_registration_linkage(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    tax_reg_id = uuid7()
    await reference_data(factory)
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/warehouses"
    created = await client.post(
        route,
        headers=command_headers(current),
        json={
            "code": "WH_GSTIN",
            "name": "Maharashtra Godown",
            "kind": "GODOWN",
            "country_code": "IN",
            "state_code": "IN-MH",
            "tax_registration_id": str(tax_reg_id),
        },
    )
    assert created.status_code == 201, created.text
    wh_id = created.json()["id"]
    assert created.json()["tax_registration_id"] == str(tax_reg_id)

    # Read back detail
    detail = await client.get(f"{route}/{wh_id}", headers=current)
    assert detail.status_code == 200
    assert detail.json()["tax_registration_id"] == str(tax_reg_id)

    # Update tax_registration_id
    new_tax_reg_id = uuid7()
    updated = await client.patch(
        f"{route}/{wh_id}",
        headers=command_headers(current),
        json={
            "tax_registration_id": str(new_tax_reg_id),
            "expected_version": created.json()["row_version"],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["tax_registration_id"] == str(new_tax_reg_id)
