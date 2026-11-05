"""Company people operations are projections, never tenant profile authority."""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Membership, RoleAssignment, UserInvitation
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_membership, build_user, seed_two_companies

pytestmark = pytest.mark.asyncio


async def test_company_people_are_affiliated_current_tenant_users_only(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        other = build_company(tenant_id=tenant_a, code="OTHER")
        users = [
            build_user(
                tenant_id=tenant_a,
                display_name=f"Person {index}",
                email=f"person{index}@example.com",
            )
            for index in range(5)
        ]
        users[4].user_type = "platform_admin"
        session.add_all([other, *users])
        await session.flush()
        session.add_all(
            [
                build_membership(tenant_id=tenant_a, company_id=company, user_id=users[0].id),
                build_membership(
                    tenant_id=tenant_a, company_id=company, user_id=users[1].id, is_active=False
                ),
                build_membership(
                    tenant_id=tenant_a,
                    company_id=company,
                    user_id=users[2].id,
                    started_on=dt.date(2099, 1, 1),
                ),
                build_membership(tenant_id=tenant_a, company_id=other.id, user_id=users[3].id),
                build_membership(tenant_id=tenant_a, company_id=company, user_id=users[4].id),
            ]
        )
        await session.commit()
        person_id, hidden_id, other_id = users[0].id, users[3].id, other.id
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["user.read"], scope_type="company", scope_id=company)],
    )
    path = f"/v1/companies/{company}/users"
    result = await client.get(path, headers=headers)
    assert result.status_code == 200, result.text
    assert [item["id"] for item in result.json()["items"]] == [str(person_id)]
    assert "phone" not in result.json()["items"][0]
    assert (await client.get(f"{path}/{person_id}", headers=headers)).status_code == 200
    assert (await client.get(f"{path}/{hidden_id}", headers=headers)).status_code == 404
    assert (await client.get(f"/v1/companies/{other_id}/users", headers=headers)).status_code == 403
    assert (await client.get(f"/v1/companies/{foreign}/users", headers=headers)).status_code == 404
    assert (await client.get("/v1/users", headers=headers)).status_code == 403
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, params={"q": "P"}, headers=headers)).status_code == 422
    assert (await client.get(path, params={"q": "Person 0", "limit": 1}, headers=headers)).json()[
        "items"
    ][0]["id"] == str(person_id)


async def test_company_invite_creates_affiliation_and_invitation_without_grants(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        actor = build_user(tenant_id=tenant_a)
        other = build_company(tenant_id=tenant_a, code="OTHER")
        session.add_all([actor, other])
        await session.commit()
        actor_id, other_id = actor.id, other.id
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=actor_id,
        grants=[grant(["user.invite"], scope_type="company", scope_id=company)],
    )
    path = f"/v1/companies/{company}/users"
    body = {"email": "new.member@example.com", "first_name": "New", "last_name": "Member"}
    result = await client.post(path, json=body, headers=headers)
    assert result.status_code == 201, result.text
    user_id = uuid.UUID(result.json()["id"])
    assert result.json()["user_type"] == "tenant_user"
    assert result.json()["status"] == "invited"
    with tenant_scope(tenant_a):
        membership = await session.scalar(select(Membership).where(Membership.user_id == user_id))
        assert membership is not None and membership.company_id == company
        assert await session.scalar(
            select(UserInvitation.id).where(UserInvitation.user_id == user_id)
        )
        assert (
            await session.scalar(
                select(RoleAssignment.id).where(RoleAssignment.subject_id == user_id)
            )
            is None
        )
    assert (await client.post(path, json=body, headers=headers)).status_code == 409
    for extra in [
        {"user_type": "platform_admin"},
        {"default_company_id": str(other_id)},
        {"reporting_manager_id": str(actor_id)},
    ]:
        assert (await client.post(path, json=body | extra, headers=headers)).status_code == 422
    assert (
        await client.post(f"/v1/companies/{other_id}/users", json=body, headers=headers)
    ).status_code == 403
    assert (
        await client.post(f"/v1/companies/{foreign}/users", json=body, headers=headers)
    ).status_code == 404
    assert (await client.post("/v1/users", json=body, headers=headers)).status_code == 403


async def test_assignment_check_is_guarded_and_has_no_effect(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from tests.factories import build_role, build_role_permission

    await seed_two_companies(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        role = build_role(tenant_id=tenant_a)
        subject = build_user(tenant_id=tenant_a)
        session.add_all([role, subject])
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role.id, permission_key="invoice.read"
            )
        )
        await session.commit()
        role_id, subject_id = role.id, subject.id
    actor_id = uuid7()
    body = {
        "subject_type": "user",
        "subject_id": str(subject_id),
        "role_id": str(role_id),
        "scope_type": "tenant",
        "grant_reason": "Review access",
    }
    headers = actor_headers(
        tenant_id=tenant_a, user_id=actor_id, grants=[grant(["role.assign", "invoice.read"])]
    )
    checked = await client.post("/v1/role-assignments/check", json=body, headers=headers)
    assert checked.status_code == 200, checked.text
    assert checked.json() == {"allowed": True}
    with tenant_scope(tenant_a):
        assert await session.scalar(select(RoleAssignment.id)) is None
    limited = actor_headers(tenant_id=tenant_a, user_id=actor_id, grants=[grant(["role.assign"])])
    assert (
        await client.post("/v1/role-assignments/check", json=body, headers=limited)
    ).status_code == 403
    assert (
        await client.post(
            "/v1/role-assignments/check", json=body | {"subject_id": str(actor_id)}, headers=headers
        )
    ).status_code in {403, 422}
    assert (await client.post("/v1/role-assignments/check", json=body)).status_code == 401


async def test_company_assignment_labels_require_current_affiliation_and_object_read(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from tests.factories import build_role, build_role_assignment

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        subject = build_user(tenant_id=tenant_a)
        role = build_role(tenant_id=tenant_a)
        other = build_company(tenant_id=tenant_a, code="OTHER")
        session.add_all([subject, role, other])
        await session.flush()
        session.add_all(
            [
                build_membership(tenant_id=tenant_a, company_id=company, user_id=subject.id),
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role.id,
                    subject_id=subject.id,
                    scope_type="company",
                    scope_id=company,
                ),
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role.id,
                    subject_id=subject.id,
                    scope_type="company",
                    scope_id=other.id,
                ),
            ]
        )
        await session.commit()
        other_id = other.id
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.read"]), grant(["user.read"], scope_type="company", scope_id=company)],
    )
    rows = (await client.get("/v1/role-assignments", headers=headers)).json()["items"]
    assert next(row for row in rows if row["scope_id"] == str(company))["subject_label"]
    assert next(row for row in rows if row["scope_id"] == str(other_id))["subject_label"] is None
