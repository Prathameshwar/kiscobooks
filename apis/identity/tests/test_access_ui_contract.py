"""Searchable access controls retain tenant and object read boundaries."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import build_field_policy, build_user, seed_two_companies

pytestmark = pytest.mark.asyncio


async def test_access_code_search_is_literal_and_tenant_bound(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["department.manage", "department.read", "group.manage", "group.read"])],
    )
    for path in ["/v1/user-groups", f"/v1/companies/{company_a}/departments"]:
        for code in ["OP_ONE", "OPXTWO", "SALES"]:
            created = await client.post(path, json={"code": code, "name": code}, headers=headers)
            assert created.status_code == 201, created.text
        result = await client.get(path, params={"q": "OP_", "limit": 1}, headers=headers)
        assert result.status_code == 200, result.text
        assert [item["code"] for item in result.json()["items"]] == ["OP_ONE"]
        assert (await client.get(path, params={"q": "O"}, headers=headers)).status_code == 422
    assert (
        await client.get(f"/v1/companies/{company_b}/departments?q=OP", headers=headers)
    ).status_code == 404


async def test_access_search_does_not_widen_directory_permissions(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.read"])])
    assert (await client.get("/v1/user-groups?q=OP", headers=headers)).status_code == 403
    assert (
        await client.get(f"/v1/companies/{company_a}/departments?q=OP", headers=headers)
    ).status_code == 403


async def test_assignment_labels_respect_profile_read_authority(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from tests.test_api_org import _seed_user

    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)
    administrator = uuid7()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=administrator,
        grants=[
            grant(
                [
                    "role.manage",
                    "role.assign",
                    "role.read",
                    "invoice.read",
                    "user.read",
                    "company.read",
                ]
            )
        ],
    )
    role = await client.post(
        "/v1/roles",
        json={"key": "access_viewer", "name": "Access Viewer", "permissions": ["invoice.read"]},
        headers=headers,
    )
    assert role.status_code == 201, role.text
    created = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": role.json()["role"]["id"],
            "scope_type": "company",
            "scope_id": str(company_a),
            "grant_reason": "UI review",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    visible = (await client.get("/v1/role-assignments", headers=headers)).json()["items"][0]
    assert visible["role_name"] == "Access Viewer"
    assert visible["subject_label"]
    assert visible["scope_label"]
    limited = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.read", "user.read"], scope_type="company", scope_id=company_a)],
    )
    private = (await client.get("/v1/role-assignments", headers=limited)).json()["items"][0]
    assert private["role_name"] == "Access Viewer"
    assert private["subject_label"] is None
    assert private["scope_label"] is None

    from billing_platform.db import tenant_scope

    with tenant_scope(tenant_a):
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=administrator,
                entity_type="identity.company",
                field_key="display_name",
                access="read",
                effect="deny",
            )
        )
        await session.commit()
    masked = (await client.get("/v1/role-assignments", headers=headers)).json()["items"][0]
    assert masked["scope_label"] is None


async def test_selected_company_and_department_resolution_retains_visibility(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from billing_platform.db import tenant_scope

    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
        user_id = user.id
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[
            grant(
                ["invoice.read", "department.manage", "department.read"],
                scope_type="company",
                scope_id=company_a,
            )
        ],
    )
    selected = await client.get(
        "/v1/session/companies", params={"id": str(company_a)}, headers=headers
    )
    assert selected.status_code == 200, selected.text
    assert [row["id"] for row in selected.json()["items"]] == [str(company_a)]
    hidden = await client.get(
        "/v1/session/companies", params={"id": str(company_b)}, headers=headers
    )
    assert hidden.status_code == 200 and hidden.json()["items"] == []
    path = f"/v1/companies/{company_a}/departments"
    created = await client.post(path, json={"code": "OPS", "name": "Operations"}, headers=headers)
    assert created.status_code == 201, created.text
    selected = await client.get(path, params={"id": created.json()["id"]}, headers=headers)
    assert selected.status_code == 200, selected.text
    assert [row["id"] for row in selected.json()["items"]] == [created.json()["id"]]
    assert (await client.get(path, params={"id": str(uuid7())}, headers=headers)).json()[
        "items"
    ] == []
