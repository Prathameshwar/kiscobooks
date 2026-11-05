from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.attribute_factories import auth
from tests.test_api import headers
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers


@pytest.mark.parametrize("path", ["attribute-definitions", "attribute-options", "attribute-sets"])
async def test_attribute_master_crud_scope_and_lists(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    path: str,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    extra: dict[str, Any] = {}
    if path == "attribute-definitions":
        extra = {"value_type": "TEXT", "is_variant_capable": True}
    elif path == "attribute-options":
        definition = await create(
            client,
            company,
            current,
            "attribute-definitions",
            {"code": "D", "name": "Definition", "value_type": "TEXT"},
        )
        assert definition.status_code == 201, definition.text
        extra = {
            "definition_id": definition.json()["id"],
            "value_type": "TEXT",
            "value_text": "Alpha",
        }
    body = {"code": "A", "name": "Alpha", **extra}
    route = f"/v1/companies/{company}/{path}"
    assert (await client.post(route, json=body)).status_code == 401
    reader = headers(company, tenant=tenant_a, user=user, permission="item.read")
    assert (await client.post(route, headers=command_headers(reader), json=body)).status_code == 403
    receipt = command_headers(current)
    response = await client.post(route, headers=receipt, json=body)
    assert response.status_code == 201, response.text
    first = response.json()
    replay = await client.post(route, headers=receipt, json=body)
    assert replay.status_code == 201 and replay.json() == first
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert (await create(client, company, current, path, body)).status_code == 409
    assert (
        await client.post(route, headers=receipt, json={**body, "name": "Different"})
    ).status_code == 422
    second_body = {
        **body,
        "code": "B",
        "name": "Beta",
        **({"value_text": "Beta"} if path == "attribute-options" else {}),
    }
    assert (await create(client, company, current, path, second_body)).status_code == 201
    page = await client.get(route, headers=current, params={"limit": 1, "sort": "-code"})
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["code"] == "B"
    assert (
        not {"value_text", "value_hash", "canonical_value", "custom_fields"}
        & page.json()["items"][0].keys()
    )
    following = await client.get(
        route,
        headers=current,
        params={"limit": 1, "sort": "-code", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert following.json()["items"][0]["code"] == "A"
    assert (await client.get(route, headers=current, params={"q": "Al"})).json()["items"][0][
        "id"
    ] == first["id"]
    for query in ("limit=0", "unknown=x", "sort=value_text", "code=A&code=B"):
        assert (await client.get(route + "?" + query, headers=current)).status_code == 422
    detail = route + "/" + first["id"]
    assert (await client.get(detail, headers=current)).status_code == 200
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    assert (
        await client.get(detail.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404
    updated = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 1, "name": "Changed"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["row_version"] == 2
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 1, "name": "Stale"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 2, "name": None}
        )
    ).status_code == 422
    noop = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 2, "name": "Changed"}
    )
    assert noop.json()["row_version"] == 2
    for action, version in (("deactivate", 2), ("activate", 3)):
        response = await client.post(
            detail + "/" + action,
            headers=command_headers(current),
            json={"expected_version": version},
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_active"] is (action == "activate")


async def test_unused_typed_fields_are_not_treated_as_writes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.snapshots import SnapshotRecord

    from tests.source_factories import all_facts

    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.attribute_option",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "value_integer",
            "access": "write",
        },
    )
    current = await auth(factory, tenant_a, company, user, facts=(*facts, deny))
    for kind, expected in (("TEXT", 201), ("INTEGER", 403)):
        definition = await create(
            client,
            company,
            current,
            "attribute-definitions",
            {"code": kind, "name": kind, "value_type": kind},
        )
        assert definition.status_code == 201
        body = {
            "code": kind,
            "name": kind,
            "definition_id": definition.json()["id"],
            "value_type": kind,
            **({"value_text": "Blue"} if kind == "TEXT" else {"value_integer": "1"}),
        }
        response = await create(client, company, current, "attribute-options", body)
        assert response.status_code == expected, response.text


async def test_integer_detail_and_native_policy_remain_exact(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.snapshots import SnapshotRecord

    from tests.source_factories import all_facts

    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    current = await auth(factory, tenant_a, company, user, facts=facts)
    definition = (
        await create(
            client,
            company,
            current,
            "attribute-definitions",
            {"code": "N", "name": "Number", "value_type": "INTEGER"},
        )
    ).json()
    body = {
        "code": "BIG",
        "name": "Big",
        "definition_id": definition["id"],
        "value_type": "INTEGER",
        "value_integer": "9007199254740993",
    }
    created = await create(client, company, current, "attribute-options", body)
    assert created.status_code == 201, created.text
    assert created.json()["value_integer"] == "9007199254740993"
    route = f"/v1/companies/{company}/attribute-options/{created.json()['id']}"
    assert "value_hash" not in created.json() and "canonical_value" not in created.json()
    assert (
        await create(client, company, current, "attribute-options", {**body, "code": "SAME"})
    ).status_code == 409
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.attribute_option",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "name",
            "condition": {"field": "value_integer", "cmp": "gt", "value": "9007199254740992"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    assert (
        await client.patch(
            route, headers=command_headers(current), json={"expected_version": 1, "name": "Denied"}
        )
    ).status_code == 403
    hidden = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.attribute_option",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "value_integer",
            "access": "read",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, hidden))
    assert "value_integer" not in (await client.get(route, headers=current)).json()


async def test_attribute_options_share_parent_bound_reference_lookup(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    definitions = []
    for code in ("FIRST", "SECOND"):
        definitions.append(
            (
                await create(
                    client,
                    company,
                    current,
                    "attribute-definitions",
                    {"code": code, "name": code, "value_type": "TEXT"},
                )
            ).json()
        )
    body = {
        "code": "BLUE",
        "name": "Blue",
        "definition_id": definitions[0]["id"],
        "value_type": "TEXT",
        "value_text": "Blue",
    }
    choice = await create(client, company, current, "attribute-options", body)
    assert choice.status_code == 201
    root = f"/v1/companies/{company}/option-sources/"
    for source in ("catalog.attribute_definitions", "catalog.attribute_sets"):
        assert (await client.get(root + source, headers=current)).status_code == 200
    assert (
        await client.get(root + "catalog.attribute_options", headers=current)
    ).status_code == 422
    page = await client.get(
        root + "catalog.attribute_options",
        headers=current,
        params={"parent_id": definitions[0]["id"]},
    )
    assert page.status_code == 200 and page.json()["items"][0]["value"] == choice.json()["id"]
    assert (
        await client.get(
            root + "catalog.attribute_options",
            headers=current,
            params={"parent_id": definitions[1]["id"]},
        )
    ).json()["items"] == []
    parent = f"/v1/companies/{company}/attribute-definitions/{definitions[0]['id']}"
    assert (
        await client.post(
            parent + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    assert (
        await client.patch(
            parent,
            headers=command_headers(current),
            json={"expected_version": 1, "code": "CHANGED"},
        )
    ).status_code == 409
    child = f"/v1/companies/{company}/attribute-options/{choice.json()['id']}"
    assert (
        await client.post(
            child + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.post(
            parent + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.get(
            root + "catalog.attribute_options",
            headers=current,
            params={"parent_id": definitions[0]["id"]},
        )
    ).status_code == 422
    assert (
        await client.post(
            child + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409


async def test_measured_options_canonical_units_and_typed_value_guards(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.source_factories import all_facts

    company, user = uuid7(), uuid7()
    current = await auth(
        factory,
        tenant_a,
        company,
        user,
        facts=tuple(row for row in all_facts(company, user) if row.kind != "field_policy"),
    )
    root = f"/v1/companies/{company}"
    units = {}
    for code, dimension in (("KG", "MASS"), ("G", "MASS"), ("M", "LENGTH"), ("OLD", "MASS")):
        response = await create(
            client,
            company,
            current,
            "units",
            {
                "code": code,
                "symbol": code,
                "name": code,
                "dimension": dimension,
                "decimal_places": 3,
                "quantity_increment": "0.001",
            },
        )
        assert response.status_code == 201, response.text
        units[code] = response.json()["id"]
    definition = (
        await create(
            client,
            company,
            current,
            "attribute-definitions",
            {
                "code": "WEIGHT",
                "name": "Weight",
                "value_type": "DECIMAL",
                "measurement_dimension": "MASS",
            },
        )
    ).json()
    body = {
        "code": "ONE",
        "name": "One kilogram",
        "definition_id": definition["id"],
        "value_type": "DECIMAL",
        "value_decimal": "1",
        "unit_id": units["KG"],
    }
    assert (await create(client, company, current, "attribute-options", body)).status_code == 409
    assert (
        await create(client, company, current, "attribute-options", {**body, "unit_id": units["M"]})
    ).status_code == 422
    assert (
        await create(client, company, current, "attribute-options", {**body, "unit_id": None})
    ).status_code == 422
    assert (
        await create(
            client, company, current, "attribute-options", {**body, "value_decimal": "0.0001"}
        )
    ).status_code == 422
    assert (
        await client.post(
            root + "/units/" + units["OLD"] + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (
        await create(
            client, company, current, "attribute-options", {**body, "unit_id": units["OLD"]}
        )
    ).status_code == 422
    for code, denominator in (("KG", "1"), ("G", "1000")):
        conversion = await create(
            client,
            company,
            current,
            "unit-conversions",
            {
                "from_unit_id": units[code],
                "canonical_unit_id": units["KG"],
                "numerator": "1",
                "denominator": denominator,
            },
        )
        assert conversion.status_code == 201, conversion.text
    first = await create(client, company, current, "attribute-options", body)
    assert first.status_code == 201, first.text
    assert first.json()["value_decimal"] == "1.0000"
    duplicate = await create(
        client,
        company,
        current,
        "attribute-options",
        {**body, "code": "GRAMS", "value_decimal": "1000", "unit_id": units["G"]},
    )
    assert duplicate.status_code == 409, duplicate.text
    different = await create(
        client,
        company,
        current,
        "attribute-options",
        {**body, "code": "GRAMS", "value_decimal": "1001", "unit_id": units["G"]},
    )
    assert different.status_code == 201, different.text
    assert (
        await client.post(
            root + "/units/" + units["G"] + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 409
    foreign_company = uuid7()
    other = await auth(
        factory,
        tenant_a,
        foreign_company,
        user,
        facts=tuple(row for row in all_facts(foreign_company, user) if row.kind != "field_policy"),
    )
    foreign_unit = (
        await create(
            client,
            foreign_company,
            other,
            "units",
            {
                "code": "KG",
                "symbol": "kg",
                "name": "Kilogram",
                "dimension": "MASS",
                "decimal_places": 3,
                "quantity_increment": "0.001",
            },
        )
    ).json()
    assert (
        await create(
            client,
            company,
            current,
            "attribute-options",
            {**body, "code": "FOREIGN", "unit_id": foreign_unit["id"]},
        )
    ).status_code == 403
    # Canonical payloads are comparison evidence, never public detail fields.
    assert not {"value_hash", "canonical_value"} & first.json().keys()


async def test_attribute_canonical_collision_fails_without_committing(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform.db import tenant_scope
    from sqlalchemy import func, select

    from catalog.domain.attributes import AttributeValue
    from catalog.models.attributes import AttributeOption

    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    definition = (
        await create(
            client,
            company,
            current,
            "attribute-definitions",
            {"code": "COLOUR", "name": "Colour", "value_type": "TEXT"},
        )
    ).json()
    body = {
        "code": "BLUE",
        "name": "Blue",
        "definition_id": definition["id"],
        "value_type": "TEXT",
        "value_text": "Blue",
    }
    assert (await create(client, company, current, "attribute-options", body)).status_code == 201
    digest, canonical = AttributeValue("TEXT", "Blue").canonical()

    def colliding(self: AttributeValue, **kwargs: Any) -> tuple[bytes, bytes]:
        return digest, canonical + b"different"

    monkeypatch.setattr(AttributeValue, "canonical", colliding)
    response = await create(
        client,
        company,
        current,
        "attribute-options",
        {**body, "code": "OTHER", "value_text": "Other"},
    )
    assert response.status_code == 409 and "collision" in response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(AttributeOption.id))) == 1


@pytest.mark.parametrize("path", ["attribute-sets", "units"])
async def test_master_version_exhaustion_rolls_back_changes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    path: str,
) -> None:
    from billing_platform.db import tenant_scope

    from catalog.models.attributes import AttributeSet
    from catalog.models.units import UnitOfMeasure
    from tests.source_factories import all_facts

    company, user = uuid7(), uuid7()
    current = await auth(
        factory,
        tenant_a,
        company,
        user,
        facts=tuple(row for row in all_facts(company, user) if row.kind != "field_policy"),
    )
    body: dict[str, Any] = {"code": "X", "name": "Original"}
    if path == "units":
        body.update(symbol="x", dimension="COUNT", decimal_places=0, quantity_increment="1")
    first = await create(client, company, current, path, body)
    assert first.status_code == 201, first.text
    detail = f"/v1/companies/{company}/{path}/{first.json()['id']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(
                AttributeSet if path == "attribute-sets" else UnitOfMeasure,
                uuid.UUID(first.json()["id"]),
            )
            assert isinstance(row, AttributeSet | UnitOfMeasure)
            row.row_version = 2**31 - 1
    rejected = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 2**31 - 1, "name": "Changed"},
    )
    assert rejected.status_code == 409, rejected.text
    final = (await client.get(detail, headers=current)).json()
    assert final["name"] == "Original" and final["row_version"] == 2**31 - 1


async def test_unreferenced_attribute_identities_can_be_edited(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    for path, extra, change in (
        (
            "attribute-definitions",
            {"value_type": "TEXT", "is_variant_capable": True},
            {"code": "NEW", "is_variant_capable": False},
        ),
        ("attribute-sets", {}, {"code": "NEW"}),
    ):
        first = await create(
            client, company, current, path, {"code": "OLD", "name": "Original", **extra}
        )
        response = await client.patch(
            f"/v1/companies/{company}/{path}/{first.json()['id']}",
            headers=command_headers(current),
            json={"expected_version": 1, **change},
        )
        assert response.status_code == 200 and response.json()["code"] == "NEW", response.text
