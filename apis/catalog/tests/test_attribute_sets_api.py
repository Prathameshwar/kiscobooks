from __future__ import annotations

import uuid
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.attributes import AttributeSetMember
from tests.attribute_factories import auth
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers


async def setup_template(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], str, list[dict[str, Any]]]:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant, company, user)
    definitions = []
    for code in ("COLOUR", "SIZE"):
        response = await create(
            client,
            company,
            current,
            "attribute-definitions",
            {"code": code, "name": code, "value_type": "TEXT", "is_variant_capable": True},
        )
        assert response.status_code == 201, response.text
        definitions.append(response.json())
    template = (
        await create(
            client, company, current, "attribute-sets", {"code": "CLOTHING", "name": "Clothing"}
        )
    ).json()
    route = f"/v1/companies/{company}/attribute-sets/{template['id']}/revisions"
    members = [
        {
            "definition_id": row["id"],
            "position": index,
            "is_required": True,
            "allow_variant_axis": True,
        }
        for index, row in enumerate(definitions)
    ]
    return company, user, current, route, members


async def test_conditional_member_denies_evaluate_fresh_values(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, route, members = await setup_template(client, factory, tenant_a)
    facts = all_facts(company, user)
    base = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **base.data,
            "entity_type": "catalog.attribute_set_member",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "position",
            "access": "write",
            "condition": {"field": "position", "cmp": "gt", "value": "1"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    key = command_headers(current)
    draft = await client.post(route, headers=key, json={"members": members})
    assert draft.status_code == 201, draft.text
    target = route + "/" + draft.json()["id"]
    replacement = [{**row, "position": 1 - row["position"]} for row in members]
    updated = await client.put(
        target + "/members",
        headers=command_headers(current),
        json={"expected_version": 1, "members": replacement},
    )
    assert updated.status_code == 200, updated.text
    denied = await client.put(
        target + "/members",
        headers=command_headers(current),
        json={"expected_version": 2, "members": [{**members[0], "position": 2}]},
    )
    assert denied.status_code == 403
    published = await client.post(
        target + "/publish", headers=command_headers(current), json={"expected_version": 2}
    )
    assert published.status_code == 200, published.text
    # Old mutable-member receipts retain the conservative current-policy check.
    assert (await client.post(route, headers=key, json={"members": members})).status_code == 403


async def test_template_draft_replace_publish_history_and_scopes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    assert (await client.post(route, json={"members": members})).status_code == 401
    reader = headers(company, tenant=tenant_a, user=user, permission="attribute_set.read")
    assert (
        await client.post(route, headers=command_headers(reader), json={"members": members})
    ).status_code == 403
    receipt = command_headers(current)
    result = await client.post(route, headers=receipt, json={"members": members})
    assert result.status_code == 201, result.text
    first = result.json()
    assert first["revision"] == 1 and first["published_at"] is None
    assert (await client.post(route, headers=receipt, json={"members": members})).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = route + "/" + first["id"]
    assert (await client.get(detail, headers=current)).status_code == 200
    page = await client.get(
        detail + "/members", headers=current, params={"limit": 1, "sort": "position"}
    )
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["definition_id"] == members[0]["definition_id"]
    follow = await client.get(
        detail + "/members",
        headers=current,
        params={"limit": 1, "sort": "position", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert follow.json()["items"][0]["definition_id"] == members[1]["definition_id"]
    old_ids = {
        row["definition_id"]: row["id"]
        for row in (await client.get(detail + "/members", headers=current)).json()["items"]
    }
    replacement = [{**member, "position": 1 - member["position"]} for member in members]
    updated = await client.put(
        detail + "/members",
        headers=command_headers(current),
        json={"expected_version": 1, "members": replacement},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["row_version"] == 2
    reordered = (await client.get(detail + "/members", headers=current)).json()["items"]
    assert reordered[0]["definition_id"] == members[1]["definition_id"]
    assert {row["definition_id"]: row["id"] for row in reordered} == old_ids
    noop = await client.put(
        detail + "/members",
        headers=command_headers(current),
        json={"expected_version": 2, "members": replacement},
    )
    assert noop.json()["row_version"] == 2
    assert (
        await client.put(
            detail + "/members",
            headers=command_headers(current),
            json={"expected_version": 1, "members": members},
        )
    ).status_code == 409
    assert (
        await client.put(
            detail + "/members",
            headers=command_headers(current),
            json={"expected_version": 2, "members": [members[0], members[0]]},
        )
    ).status_code == 422
    editor = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["attribute_set.read", "attribute_set.manage"],
    )
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(editor), json={"expected_version": 2}
        )
    ).status_code == 403
    publish_receipt = command_headers(current)
    published = await client.post(
        detail + "/publish", headers=publish_receipt, json={"expected_version": 2}
    )
    assert (
        published.status_code == 200
        and published.json()["published_at"]
        and published.json()["row_version"] == 3
    ), published.text
    assert (
        await client.post(
            detail + "/publish", headers=publish_receipt, json={"expected_version": 2}
        )
    ).headers["Idempotency-Replayed"] == "true"
    assert (
        await client.put(
            detail + "/members",
            headers=command_headers(current),
            json={"expected_version": 3, "members": []},
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 409
    second = await client.post(route, headers=command_headers(current), json={})
    assert second.status_code == 201 and second.json()["revision"] == 2
    assert (
        await client.post(
            route + "/" + second.json()["id"] + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 422
    for published_filter, expected_id in ((True, first["id"]), (False, second.json()["id"])):
        page = await client.get(route, headers=current, params={"published": published_filter})
        assert page.status_code == 200 and page.json()["items"][0]["id"] == expected_id
    for target in (route, detail + "/members"):
        assert (
            await client.get(target, headers=current, params={"q": "unsupported"})
        ).status_code == 422
    selected = await client.get(
        detail + "/members",
        headers=current,
        params={"definition_id": members[0]["definition_id"], "is_required": True},
    )
    assert len(selected.json()["items"]) == 1
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    assert (
        await client.get(detail.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404
    wrong = (
        await create(client, company, current, "attribute-sets", {"code": "OTHER", "name": "Other"})
    ).json()
    wrong_path = detail.replace(route.split("/")[5], wrong["id"])
    assert (await client.get(wrong_path, headers=current)).status_code == 403
    assert (await client.get(wrong_path + "/members", headers=current)).status_code == 403
    definition_route = (
        f"/v1/companies/{company}/attribute-definitions/{members[0]['definition_id']}"
    )
    for change in ({"code": "OTHER"}, {"is_variant_capable": False}):
        assert (
            await client.patch(
                definition_route,
                headers=command_headers(current),
                json={"expected_version": 1, **change},
            )
        ).status_code == 409
    assert (
        await client.post(
            definition_route + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 409
    master = route.rsplit("/", 1)[0]
    assert (
        await client.patch(
            master,
            headers=command_headers(current),
            json={"expected_version": 1, "code": "OTHER-CODE"},
        )
    ).status_code == 409


async def test_member_permissions_protect_replace_publish_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    receipt = command_headers(current)
    result = await client.post(route, headers=receipt, json={"members": members})
    assert result.status_code == 201, result.text
    detail = route + "/" + result.json()["id"]
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.attribute_set_member",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "is_required",
            "access": "write",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    assert (await client.post(route, headers=receipt, json={"members": members})).status_code == 403
    assert (
        await client.put(
            detail + "/members",
            headers=command_headers(current),
            json={"expected_version": 1, "members": []},
        )
    ).status_code == 403
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(AttributeSetMember)))) == 2
    hidden = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.attribute_set_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "attribute_set_id",
            "access": "read",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, hidden))
    for target in (detail, detail + "/members", route):
        assert (await client.get(target, headers=current)).status_code == 403


async def test_template_replacement_preserves_retained_identity_and_rejects_bad_members(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    first = await client.post(route, headers=command_headers(current), json={"members": members})
    detail = route + "/" + first.json()["id"]
    original = (await client.get(detail + "/members", headers=current)).json()["items"]
    new_definition = (
        await create(
            client,
            company,
            current,
            "attribute-definitions",
            {"code": "MATERIAL", "name": "Material", "value_type": "TEXT"},
        )
    ).json()
    replacement = [members[0], {"definition_id": new_definition["id"], "position": 1}]
    replaced = await client.put(
        detail + "/members",
        headers=command_headers(current),
        json={"expected_version": 1, "members": replacement},
    )
    assert replaced.status_code == 200 and replaced.json()["row_version"] == 2, replaced.text
    page = await client.get(detail + "/members", headers=current)
    rows = page.json()["items"]
    assert rows[0]["id"] == original[0]["id"]
    assert rows[1]["id"] != original[1]["id"]
    assert rows[1]["definition_id"] == new_definition["id"]
    assert (
        await client.get(detail + "/members", headers=current, params={"q": "material"})
    ).status_code == 422
    filtered = await client.get(detail + "/members", headers=current, params={"is_required": False})
    assert [item["id"] for item in filtered.json()["items"]] == [rows[1]["id"]]
    bad = [members[0], {**replacement[1], "allow_variant_axis": True}]
    assert (
        await client.put(
            detail + "/members",
            headers=command_headers(current),
            json={"expected_version": 2, "members": bad},
        )
    ).status_code == 422
    definition_path = f"/v1/companies/{company}/attribute-definitions/{new_definition['id']}"
    assert (
        await client.post(
            definition_path + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 422
    assert (await client.get(detail, headers=current)).json()["row_version"] == 2
    assert (await client.get(detail + "/members", headers=current)).json()["items"] == rows
    assert (
        await client.post(
            definition_path + "/activate",
            headers=command_headers(current),
            json={"expected_version": 2},
        )
    ).status_code == 200
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200


async def test_member_hidden_revision_denies_browsing(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    first = await client.post(route, headers=command_headers(current), json={"members": members})
    detail = route + "/" + first.json()["id"]
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.attribute_set_member",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "revision_id",
            "access": "read",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    assert (await client.get(detail + "/members", headers=current)).status_code == 403
    assert (await client.get(detail, headers=current)).status_code == 200


async def test_inactive_templates_and_oversized_requests_are_rejected(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    first = await client.post(route, headers=command_headers(current), json={"members": members})
    detail = route + "/" + first.json()["id"]
    assert (
        await client.post(
            route, headers=command_headers(current), json={"members": [members[0]] * 129}
        )
    ).status_code == 422
    assert (
        await client.post(
            route.rsplit("/", 1)[0] + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (await client.post(route, headers=command_headers(current), json={})).status_code == 409
    assert (
        await client.put(
            detail + "/members",
            headers=command_headers(current),
            json={"expected_version": 1, "members": []},
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    assert (await client.get(detail, headers=current)).json()["row_version"] == 1


async def test_template_field_metadata_marks_server_owned_fields_readonly(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    for entity, fixed in (
        ("attribute_set_revision", {"attribute_set_id", "revision", "row_version", "published_at"}),
        ("attribute_set_member", {"revision_id"}),
    ):
        response = await client.get(
            f"/v1/companies/{company}/entities/catalog.{entity}/field-set", headers=current
        )
        assert response.status_code == 200, response.text
        fields = {row["key"]: row for row in response.json()["fields"]}
        assert all(not fields[key]["writable"] for key in fixed)
        if entity == "attribute_set_member":
            assert fields["is_required"]["writable"]


async def test_exhausted_template_version_preserves_members_and_audit(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models.attributes import AttributeSetRevision

    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    first = await client.post(route, headers=command_headers(current), json={"members": members})
    detail = route + "/" + first.json()["id"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(AttributeSetRevision, uuid.UUID(first.json()["id"]))
            assert row is not None
            row.row_version = 2**31 - 1
    rejected = await client.put(
        detail + "/members",
        headers=command_headers(current),
        json={"expected_version": 2**31 - 1, "members": []},
    )
    assert rejected.status_code == 409, rejected.text
    assert (await client.get(detail, headers=current)).json()["row_version"] == 2**31 - 1
    assert len((await client.get(detail + "/members", headers=current)).json()["items"]) == 2


async def test_template_command_boundary_rejects_unavailable_lifecycle_action(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    import datetime as dt

    import pytest
    from billing_platform.authz import Grant, Scope
    from billing_platform.errors import ValidationFailedError
    from billing_platform.gateway import Actor

    from catalog.schemas.units import ExpectedVersion
    from catalog.tasks.commercial_history import SET_REVISION, command
    from tests.attribute_factories import seed_attributes

    company, user = uuid7(), uuid7()
    await auth(factory, tenant_a, company, user)
    ids = await seed_attributes(factory, tenant_a, company)
    actor = Actor(
        tenant_a,
        user,
        grants=(
            Grant(
                permissions=frozenset({"attribute_set.read", "attribute_set.manage"}),
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
            SET_REVISION,
            key=str(uuid7()),
            body=ExpectedVersion(expected_version=1),
            action="close",
            object_id=ids["attribute_set_revision"],
            parent_id=ids["attribute_set"],
        )
