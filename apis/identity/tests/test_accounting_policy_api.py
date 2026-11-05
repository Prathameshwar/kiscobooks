"""Accounting policy administration must work through Identity's supported APIs."""

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.services.accounting_context import company_context
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_role,
    build_role_assignment,
    build_user,
    build_user_group,
    build_user_group_member,
    seed_two_companies,
)

PERMISSIONS = [
    "field_policy.manage",
    "field_config.manage",
    "accounting.party.read",
    "accounting.party.manage",
]


async def seed(session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID):
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    admin, reader, third = uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add_all(
            [
                build_user(tenant_id=tenant_a, user_id=value, email=f"{value}@example.test")
                for value in (admin, reader, third)
            ]
        )
        await session.commit()
    return company, other, admin, reader, third


def policy(reader: uuid.UUID, company: uuid.UUID) -> dict:
    return {
        "entity_type": "accounting.party",
        "subject_type": "user",
        "subject_id": str(reader),
        "field_key": "notes",
        "access": "read",
        "effect": "deny",
        "reason": "Restricted",
        "scope_type": "company",
        "scope_id": str(company),
        "condition": {"field": "status", "cmp": "eq", "value": "ACTIVE"},
    }


async def test_accounting_policies_and_layouts_reach_company_context(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _, admin, reader, _ = await seed(session, tenant_a, tenant_b)
    h = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    body = policy(reader, company)
    created = await client.post("/v1/field-policies", json=body, headers=h)
    assert created.status_code == 201, created.text
    configured = await client.put(
        "/v1/entities/accounting.party/field-config/notes",
        json={"label_override": "Private note", "is_visible": False},
        headers=h,
    )
    assert configured.status_code == 200, configured.text
    listing = await client.get("/v1/field-policies?entity_type=accounting.party", headers=h)
    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["items"]] == [created.json()["id"]]
    layouts = await client.get("/v1/entities/accounting.party/field-config", headers=h)
    assert layouts.status_code == 200 and len(layouts.json()["items"]) == 1
    with tenant_scope(tenant_a):
        context = await company_context(session, Actor(tenant_a, reader), company)
    assert len(context.policies) == 1 and context.policies[0]["field_key"] == "notes"
    assert context.layouts[0]["label_override"] == "Private note"
    changed = await client.put(
        f'/v1/field-policies/{created.json()["id"]}', json=body | {"is_active": False}, headers=h
    )
    assert changed.status_code == 200, changed.text


async def test_accounting_policy_authoring_checks_field_scope_and_permission(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, other, admin, reader, _ = await seed(session, tenant_a, tenant_b)
    h = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    body = policy(reader, company)
    missing = actor_headers(
        tenant_id=tenant_a, user_id=admin, grants=[grant(["field_policy.manage"])]
    )
    assert (await client.post("/v1/field-policies", json=body, headers=missing)).status_code == 403
    assert (await client.post("/v1/field-policies", json=body)).status_code == 401
    for invalid in (
        {"field_key": "unknown"},
        {"entity_type": "accounting.unknown"},
        {"condition": {"field": "secret", "cmp": "eq", "value": "x"}},
    ):
        response = await client.post("/v1/field-policies", json=body | invalid, headers=h)
        assert response.status_code == 422, response.text
    foreign = await client.post("/v1/field-policies", json=policy(reader, other), headers=h)
    assert foreign.status_code == 422, foreign.text
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=admin,
        grants=[grant(PERMISSIONS, scope_type="company", scope_id=company)],
    )
    tenant = body | {"scope_type": "tenant", "scope_id": None}
    assert (await client.post("/v1/field-policies", json=tenant, headers=scoped)).status_code == 403


async def test_accounting_policy_cannot_self_grant_or_delegate_denied_access(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _, admin, reader, third = await seed(session, tenant_a, tenant_b)
    h = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    denied = await client.post("/v1/field-policies", json=policy(reader, company), headers=h)
    assert denied.status_code == 201, denied.text
    self_edit = await client.post("/v1/field-policies", json=policy(admin, company), headers=h)
    assert self_edit.status_code == 403
    reader_h = actor_headers(tenant_id=tenant_a, user_id=reader, grants=[grant(PERMISSIONS)])
    delegate = await client.post(
        "/v1/field-policies",
        headers=reader_h,
        json=policy(third, company) | {"effect": "allow", "condition": None},
    )
    assert delegate.status_code == 403, delegate.text


async def test_accounting_layout_cannot_hide_required_fields_or_invent_fields(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    _, _, admin, _, _ = await seed(session, tenant_a, tenant_b)
    h = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    for field, values in [
        ("code", {"is_visible": False}),
        ("unknown", {"is_visible": False}),
        ("notes", {"is_required": True}),
    ]:
        response = await client.put(
            f"/v1/entities/accounting.party/field-config/{field}", json=values, headers=h
        )
        assert response.status_code == 422, response.text


async def test_completed_master_fields_can_be_administered_and_signed(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _, admin, reader, _ = await seed(session, tenant_a, tenant_b)
    fields = [
        ("account_group_alias", "alias", "group"),
        ("account_group", "allocation_method", "group"),
        ("account", "rounding_limit", "account"),
        ("account_tax_profile", "duty_type", "tax"),
    ]
    permissions = PERMISSIONS + [
        f"accounting.{resource}.{action}"
        for resource in ("group", "account", "tax")
        for action in ("read", "manage")
    ]
    h = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(permissions)])
    for resource, field, _ in fields:
        entity = "accounting." + resource
        body = policy(reader, company) | {
            "entity_type": entity,
            "field_key": field,
            "condition": None,
        }
        created = await client.post("/v1/field-policies", json=body, headers=h)
        assert created.status_code == 201, created.text
        configured = await client.put(
            f"/v1/entities/{entity}/field-config/{field}",
            json={"label_override": "Master setting"},
            headers=h,
        )
        assert configured.status_code == 200, configured.text
    with tenant_scope(tenant_a):
        context = await company_context(session, Actor(tenant_a, reader), company)
    assert {(row["entity_type"], row["field_key"]) for row in context.policies} == {
        ("accounting." + resource, field) for resource, field, _ in fields
    }
    assert len(context.layouts) == len(fields)


async def test_company_grant_cannot_administer_accounting_field_authority(
    client,
    session,
    tenant_a,
    tenant_b,
) -> None:
    company, _, admin, reader, _ = await seed(session, tenant_a, tenant_b)
    h = actor_headers(
        tenant_id=tenant_a,
        user_id=admin,
        grants=[grant(PERMISSIONS, scope_type="company", scope_id=company)],
    )
    response = await client.post("/v1/field-policies", headers=h, json=policy(reader, company))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    "expired,inactive,other_scope,expected",
    [
        (False, False, False, 2),
        (True, False, False, 1),
        (False, True, False, 0),
        (False, False, True, 1),
    ],
)
async def test_context_respects_group_activity_role_validity_and_company_scope(
    client,
    session,
    tenant_a,
    tenant_b,
    expired,
    inactive,
    other_scope,
    expected,
) -> None:
    company, _, admin, reader, _ = await seed(session, tenant_a, tenant_b)
    group_id, role_id, second_company = uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_company(tenant_id=tenant_a, company_id=second_company, code="SECOND"))
        session.add(build_user_group(tenant_id=tenant_a, group_id=group_id, is_active=not inactive))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id))
        await session.flush()
        session.add(
            build_user_group_member(tenant_id=tenant_a, user_group_id=group_id, user_id=reader)
        )
        session.add(
            build_role_assignment(
                tenant_id=tenant_a,
                role_id=role_id,
                subject_id=group_id,
                subject_type="user_group",
                scope_type="company",
                scope_id=second_company if other_scope else company,
                valid_to=dt.date.today() - dt.timedelta(days=1) if expired else None,
            )
        )
        await session.commit()
    h = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    for subject_type, identifier in [("user_group", group_id), ("role", role_id)]:
        body = policy(identifier, company) | {"subject_type": subject_type}
        response = await client.post("/v1/field-policies", headers=h, json=body)
        assert response.status_code == 201, response.text
    with tenant_scope(tenant_a):
        context = await company_context(
            session, Actor(tenant_a, reader, group_ids=frozenset({group_id})), company
        )
    assert len(context.policies) == expected
