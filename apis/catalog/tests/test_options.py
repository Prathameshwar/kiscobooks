from __future__ import annotations

import uuid
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.units import PackType, UnitOfMeasure
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import create, setup_source


async def test_option_lists_are_paged_scoped_searchable_and_protected(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    groups = []
    for code in ("A", "B", "C"):
        response = await create(
            client,
            company,
            auth,
            "item-groups",
            {"code": code, "name": "Group " + code, "valid_from": "2020-01-01"},
        )
        assert response.status_code == 201, response.text
        groups.append(response.json())
    base = f"/v1/companies/{company}/option-sources/catalog.item_groups"
    assert (await client.get(base)).status_code == 401
    assert (
        await client.get(
            base, headers=headers(uuid7(), permission="item_group.read", tenant=tenant_a, user=user)
        )
    ).status_code == 403
    assert (
        await client.get(
            base, headers=headers(company, permission="unit.read", tenant=tenant_a, user=user)
        )
    ).status_code == 403
    response = await client.get(base + "?limit=1", headers=auth)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["items"] == [{"value": groups[0]["id"], "code": "A", "label": "Group A"}]
    cursor = page["page"]["next_cursor"]
    second = await client.get(base, params={"limit": 1, "cursor": cursor}, headers=auth)
    assert second.json()["items"][0]["code"] == "B"
    assert (
        await client.get(base, params={"limit": 1, "cursor": cursor, "sort": "-name"}, headers=auth)
    ).status_code == 422
    assert (await client.get(base + "?sort=-name&q=Group%20C", headers=auth)).json()["items"][0][
        "code"
    ] == "C"
    for suffix in (
        "?parent_id=" + str(uuid7()),
        "?limit=201",
        "?unknown=x",
        "?sort=custom_fields",
        "?q=A&q=B",
    ):
        assert (await client.get(base + suffix, headers=auth)).status_code == 422
    assert (
        await client.get(base.replace("catalog.item_groups", "https:external"), headers=auth)
    ).status_code == 422
    await client.post(
        f"/v1/companies/{company}/item-groups/{groups[1]['id']}/deactivate",
        json={"expected_version": 1},
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert [row["code"] for row in (await client.get(base, headers=auth)).json()["items"]] == [
        "A",
        "C",
    ]
    # Another tenant cannot reuse a company UUID to read this tenant's masters.
    other_user = uuid7()
    other_auth = await setup_source(factory, tenant_b, company, other_user)
    assert (await client.get(base, headers=other_auth)).json()["items"] == []
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.item_group",
            "field_key": "name",
            "access": "read",
            "subject_type": "user",
            "subject_id": str(user),
        },
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=(*facts, deny), version=3)
    assert (await client.get(base, headers=auth)).status_code == 403


async def test_parent_options_cannot_cross_scheme_or_reuse_cursor(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    schemes = []
    for code in ("A", "B"):
        response = await create(
            client,
            company,
            auth,
            "category-schemes",
            {"code": code, "name": code, "membership_mode": "SINGLE"},
        )
        schemes.append(response.json()["id"])
    for code, scheme in (("A", schemes[0]), ("B", schemes[0]), ("C", schemes[1])):
        assert (
            await create(
                client,
                company,
                auth,
                "item-categories",
                {"code": code, "name": code, "scheme_id": scheme},
            )
        ).status_code == 201
    base = f"/v1/companies/{company}/option-sources/catalog.item_categories"
    assert (await client.get(base, headers=auth)).status_code == 422
    assert (
        await client.get(base, params={"parent_id": str(uuid7())}, headers=auth)
    ).status_code == 422
    first = (
        await client.get(base, params={"parent_id": schemes[0], "limit": 1}, headers=auth)
    ).json()
    assert first["items"][0]["code"] == "A"
    assert (
        await client.get(
            base,
            params={"parent_id": schemes[1], "limit": 1, "cursor": first["page"]["next_cursor"]},
            headers=auth,
        )
    ).status_code == 422
    assert (await client.get(base, params={"parent_id": schemes[1]}, headers=auth)).json()["items"][
        0
    ]["code"] == "C"
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    for number, (entity, key) in enumerate(
        (("catalog.item_category", "scheme_id"), ("catalog.category_scheme", "is_active")), start=3
    ):
        deny = SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                **policy.data,
                "entity_type": entity,
                "field_key": key,
                "access": "read",
                "subject_type": "user",
                "subject_id": str(user),
            },
        )
        auth = await setup_source(
            factory, tenant_a, company, user, facts=(*facts, deny), version=number
        )
        assert (
            await client.get(base, params={"parent_id": schemes[0]}, headers=auth)
        ).status_code == 403


def custom_facts(company: uuid.UUID, user: uuid.UUID, **changes: Any) -> tuple[SnapshotRecord, ...]:
    return tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "entity_type": "catalog.item_group",
                **(changes if row.kind == "custom_definition" else {}),
            },
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in all_facts(company, user)
    )


async def test_dynamic_reference_validation_uses_current_local_master_and_metadata(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, pack = uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                PackType(id=pack, tenant_id=tenant_a, company_id=company, code="BOX", name="Box")
            )
            db.add(
                UnitOfMeasure(
                    tenant_id=tenant_a,
                    company_id=company,
                    code="EA",
                    symbol="ea",
                    name="Each",
                    dimension="COUNT",
                    decimal_places=0,
                    quantity_increment="1",
                )
            )
    facts = custom_facts(
        company,
        user,
        data_type="dynamic_select",
        option_source_key="catalog.pack_types",
        help_text="Choose pack",
        placeholder="Pack",
        display_group="Packaging",
    )
    await setup_source(factory, tenant_a, company, user, facts=facts)
    auth = headers(
        company,
        permission=["item_group.read", "item_group.manage", "pack_type.read", "unit.read"],
        tenant=tenant_a,
        user=user,
    )
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.item_group/field-set", headers=auth
    )
    field = next(row for row in metadata.json()["fields"] if row["key"] == "cf_note")
    assert (
        field["custom"]["data_type"] == "dynamic_select"
        and field["custom"]["option_source_key"] == "catalog.pack_types"
    )
    assert field["help_text"] == "Choose pack" and field["display_group"] == "Packaging"
    body = {
        "code": "A",
        "name": "A",
        "valid_from": "2020-01-01",
        "custom_fields": {"cf_note": str(pack)},
    }
    created = await create(client, company, auth, "item-groups", body)
    assert created.status_code == 201, created.text
    for value in (str(uuid7()), "not-an-id"):
        response = await create(
            client,
            company,
            auth,
            "item-groups",
            {**body, "code": "B", "custom_fields": {"cf_note": value}},
        )
        assert response.status_code == 422, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(PackType, pack)
            assert row is not None
            row.is_active = False
    assert (
        await create(client, company, auth, "item-groups", {**body, "code": "B"})
    ).status_code == 422
    # Historical values survive unrelated updates after an option is retired.
    response = await client.patch(
        f"/v1/companies/{company}/item-groups/{created.json()['id']}",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1, "name": "Changed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["custom_fields"]["cf_note"] == str(pack)
    options = f"/v1/companies/{company}/option-sources"
    assert (await client.get(options + "/catalog.units", headers=auth)).json()["items"][0][
        "code"
    ] == "EA"
    assert (await client.get(options + "/catalog.pack_types", headers=auth)).json()["items"] == []


async def test_custom_layout_defaults_and_safe_metadata_conditions(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = custom_facts(
        company,
        user,
        data_type="boolean",
        default_value="false",
        help_text="Original",
        placeholder="Choose",
        display_group="Old",
    )
    facts = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "default_value": "true",
                "help_text_override": "Configured",
                "display_group": "New",
            },
        )
        if row.kind == "field_config"
        else row
        for row in facts
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=facts)
    metadata_path = f"/v1/companies/{company}/entities/catalog.item_group/field-set"
    metadata = (await client.get(metadata_path, headers=auth)).json()
    field = next(row for row in metadata["fields"] if row["key"] == "cf_note")
    assert field["custom"]["default_value"] is True and field["help_text"] == "Configured"
    assert field["display_group"] == "New" and field["placeholder"] == "Choose"
    created = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["custom_fields"] == {"cf_note": True}
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.item_group",
            "field_key": "allowed_kind",
            "access": "read",
            "subject_type": "user",
            "subject_id": str(user),
        },
    )
    conditional = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "visibility": {"field": "allowed_kind", "cmp": "eq", "value": "BOTH"},
            },
        )
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    auth = await setup_source(
        factory, tenant_a, company, user, facts=(*conditional, deny), version=3
    )
    field = next(
        row
        for row in (await client.get(metadata_path, headers=auth)).json()["fields"]
        if row["key"] == "cf_note"
    )
    assert field["custom"]["visibility"] is None and field["conditional_access"] is True
    assert field["writable"] is False
    invalid = tuple(
        SnapshotRecord(kind=row.kind, id=row.id, data={**row.data, "default_value": "not-json"})
        if row.kind == "field_config"
        else row
        for row in facts
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=invalid, version=4)
    assert (await client.get(metadata_path, headers=auth)).status_code == 503


async def test_dynamic_category_parent_change_and_source_contract(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    schemes = []
    for code in ("S1", "S2"):
        response = await create(
            client,
            company,
            auth,
            "category-schemes",
            {"code": code, "name": code, "membership_mode": "SINGLE"},
        )
        schemes.append(response.json()["id"])
    category = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "CAT", "name": "Category", "scheme_id": schemes[0]},
    )
    assert category.status_code == 201
    facts = custom_facts(
        company,
        user,
        data_type="dynamic_select",
        option_source_key="catalog.category_schemes",
        default_value=schemes[0],
    )
    template = next(row for row in facts if row.kind == "custom_definition")
    child = SnapshotRecord(
        kind="custom_definition",
        id=uuid7(),
        data={
            **template.data,
            "key": "cf_category",
            "label": "Category",
            "option_source_key": "catalog.item_categories",
            "depends_on_key": "cf_note",
            "default_value": category.json()["id"],
        },
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=(*facts, child), version=3)
    created = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["custom_fields"]["cf_category"] == category.json()["id"]
    response = await client.patch(
        f"/v1/companies/{company}/item-groups/{created.json()['id']}",
        json={"expected_version": 1, "custom_fields": {"cf_note": schemes[1]}},
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert response.status_code == 422, response.text
    # Explicit clearing removes the child and permits its parent to change.
    response = await client.patch(
        f"/v1/companies/{company}/item-groups/{created.json()['id']}",
        json={"expected_version": 1, "custom_fields": {"cf_note": schemes[1], "cf_category": None}},
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert response.status_code == 200, response.text
    invalid_parents: tuple[dict[str, Any], ...] = (
        {"depends_on_key": None},
        {"depends_on_key": "name"},
    )
    for number, changes in enumerate(invalid_parents, start=4):
        invalid = child.model_copy(update={"data": {**child.data, **changes}})
        auth = await setup_source(
            factory, tenant_a, company, user, facts=(*facts, invalid), version=number
        )
        assert (
            await client.get(
                f"/v1/companies/{company}/entities/catalog.item_group/field-set", headers=auth
            )
        ).status_code == 503
