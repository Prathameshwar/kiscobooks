from __future__ import annotations

import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import (
    build_role,
    build_role_assignment,
    build_user,
    build_user_group,
    build_user_group_member,
    seed_two_companies,
)
from tests.test_gap_customization import PERMISSIONS


async def test_definition_administration_contracts_and_typed_search(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMISSIONS)])
    root = "/v1/custom-field-definitions"
    example = {
        "label": "Custom value",
        "definition": {
            "key": "cf_contract",
            "data_type": "text",
            "validation": {"max_length": 20},
            "is_searchable": True,
        },
    }
    created = await client.post(root, headers=headers, json=example)
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    detail = await client.get(root + "/" + did, headers=headers)
    assert detail.status_code == 200
    assert (await client.get(root, headers=headers)).json()["items"][0]["id"] == did
    assert (await client.get(root + f"/{uuid7()}", headers=headers)).status_code == 404
    assert (
        await client.put(root + f"/{uuid7()}", headers=headers, json=example)
    ).status_code == 404
    renamed = await client.put(
        root + "/" + did, headers=headers, json={**example, "label": "Renamed"}
    )
    assert renamed.status_code == 200, renamed.text
    for patch, expected in [
        ({"definition": {**example["definition"], "key": "cf_changed"}}, 422),
        ({"definition": {**example["definition"], "data_type": "integer"}}, 422),
        (
            {
                "definition": {
                    **example["definition"],
                    "validation": {"required": True, "max_length": 20},
                }
            },
            409,
        ),
        ({"requires_feature": "unknown"}, 422),
        ({"company_id": str(foreign)}, 422),
        ({"company_id": str(uuid7())}, 422),
    ]:
        result = await client.put(root + "/" + did, headers=headers, json={**example, **patch})
        assert result.status_code == expected, result.text
    for definition in [
        {"key": "cf_required", "data_type": "text", "validation": {"required": True}},
        {"key": "cf_default", "data_type": "integer", "default_value": 3},
    ]:
        assert (
            await client.post(
                root, headers=headers, json={"label": "Backfill first", "definition": definition}
            )
        ).status_code == 409
    for definition in [
        {"key": "cf_" + "x" * 59, "data_type": "text"},
        {"key": "cf_long", "data_type": "text", "is_searchable": True},
        {"key": "cf_default_bad", "data_type": "integer", "default_value": "invalid"},
        {
            "key": "cf_fiscal",
            "data_type": "auto_number",
            "sequence_config": {"reset": "fiscal_year"},
        },
    ]:
        response = await client.post(
            root, headers=headers, json={"label": "Invalid contract", "definition": definition}
        )
        assert response.status_code == 422, response.text
    for data_type, value, raw in [
        ("integer", 12, "12"),
        ("decimal", "12.3400", "12.34"),
        ("boolean", True, "true"),
        ("date", "2026-09-12", "2026-09-12"),
        ("datetime", "2026-09-12T00:00:00Z", "2026-09-12T00:00:00Z"),
    ]:
        key = "cf_" + data_type
        response = await client.post(
            root,
            headers=headers,
            json={
                "label": data_type,
                "definition": {"key": key, "data_type": data_type, "is_searchable": True},
            },
        )
        assert response.status_code == 201, response.text
        written = await client.patch(
            f"/v1/companies/{company}", headers=headers, json={"custom_fields": {key: value}}
        )
        assert written.status_code == 200, written.text
        listed = await client.get(
            "/v1/companies", headers=headers, params={"custom_field": key, "custom_value": raw}
        )
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()["items"]] == [str(company)]
        bad = await client.get(
            "/v1/companies",
            headers=headers,
            params={"custom_field": key, "custom_value": "invalid"},
        )
        assert bad.status_code == 422
    override = {**example, "company_id": str(company)}
    response = await client.post(root, headers=headers, json=override)
    assert response.status_code == 201, response.text
    override_id = response.json()["id"]
    for active in (False, True):
        changed = await client.put(
            root + "/" + override_id,
            headers=headers,
            json={**override, "definition": {**example["definition"], "is_active": active}},
        )
        assert changed.status_code == 200, changed.text
    foreign_headers = actor_headers(
        tenant_id=tenant_b, user_id=uuid7(), grants=[grant(PERMISSIONS)]
    )
    assert (await client.get(root, headers=foreign_headers)).json()["items"] == []
    assert (await client.get(root + "/" + did, headers=foreign_headers)).status_code == 404


async def test_layout_and_field_policy_lifecycle_scope_and_self_guards(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    admin, target = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        group = build_user_group(tenant_id=tenant_a)
        role = build_role(tenant_id=tenant_a)
        session.add_all(
            [
                build_user(tenant_id=tenant_a, user_id=admin),
                build_user(tenant_id=tenant_a, user_id=target, email="target@example.test"),
                group,
                role,
            ]
        )
        await session.flush()
        session.add(
            build_user_group_member(tenant_id=tenant_a, user_group_id=group.id, user_id=admin)
        )
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role.id, subject_id=admin))
        await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    layout = "/v1/entities/identity.company/field-config"
    for body in (
        {"label_override": "Registered name"},
        {"label_override": "Legal name", "display_order": 4},
    ):
        response = await client.put(layout + "/trade_name", headers=headers, json=body)
        assert response.status_code == 200, response.text
    assert len((await client.get(layout, headers=headers)).json()["items"]) == 1
    for url, body in [
        (layout + "/unknown", {}),
        (layout + "/trade_name", {"is_required": True}),
        (layout.replace("identity.company", "identity.unknown") + "/trade_name", {}),
    ]:
        assert (await client.put(url, headers=headers, json=body)).status_code == 422
    assert (
        await client.get(layout.replace("identity.company", "unknown"), headers=headers)
    ).status_code == 422
    policy = {
        "subject_type": "user",
        "subject_id": str(target),
        "field_key": "trade_name",
        "access": "write",
        "effect": "deny",
        "reason": "restricted",
    }
    response = await client.post("/v1/field-policies", headers=headers, json=policy)
    assert response.status_code == 201, response.text
    policy_id = response.json()["id"]
    for active in (False, True):
        changed = await client.put(
            "/v1/field-policies/" + policy_id,
            headers=headers,
            json={
                **policy,
                "is_active": active,
                "condition": {"field": "country_code", "cmp": "eq", "value": "IN"},
            },
        )
        assert changed.status_code == 200, changed.text
    assert (await client.get("/v1/field-policies", headers=headers)).json()["items"][0][
        "id"
    ] == policy_id
    assert (
        await client.put(
            "/v1/field-policies/" + policy_id,
            headers=headers,
            json={**policy, "field_key": "display_name"},
        )
    ).status_code == 422
    assert (
        await client.put(f"/v1/field-policies/{uuid7()}", headers=headers, json=policy)
    ).status_code == 404
    for body, status in [
        ({**policy, "subject_id": str(admin)}, 403),
        ({**policy, "subject_type": "role", "subject_id": str(role.id)}, 403),
        ({**policy, "subject_type": "user_group", "subject_id": str(group.id)}, 403),
        ({**policy, "subject_id": str(uuid7())}, 422),
        ({**policy, "field_key": "invalid"}, 422),
        ({**policy, "condition": {"field": "missing", "cmp": "eq", "value": 1}}, 422),
    ]:
        rejected = await client.post("/v1/field-policies", headers=headers, json=body)
        assert rejected.status_code == status, rejected.text
    foreign_headers = actor_headers(
        tenant_id=tenant_b, user_id=uuid7(), grants=[grant(PERMISSIONS)]
    )
    assert (await client.get("/v1/field-policies", headers=foreign_headers)).json()["items"] == []
