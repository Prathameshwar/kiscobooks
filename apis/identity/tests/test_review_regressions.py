"""HTTP regressions for the September Identity review (B01-B15)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import pytest_asyncio
from billing_platform.db import tenant_scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Outbox
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_company_address,
    build_department,
    build_field_policy,
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    build_user_group,
    seed_two_companies,
)


@dataclass
class Review:
    tenant: uuid.UUID
    foreign: uuid.UUID
    company: uuid.UUID
    other_company: uuid.UUID
    foreign_company: uuid.UUID
    actor: uuid.UUID
    user: uuid.UUID
    foreign_user: uuid.UUID
    department: uuid.UUID
    foreign_department: uuid.UUID
    foreign_address: uuid.UUID
    role: uuid.UUID
    group: uuid.UUID

    def headers(self, *permissions: str, **scope: Any) -> dict[str, str]:
        return actor_headers(
            tenant_id=self.tenant, user_id=self.actor, grants=[grant(list(permissions), **scope)]
        )


@pytest_asyncio.fixture
async def review(session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID) -> Review:
    ca, cb = await seed_two_companies(session, tenant_a, tenant_b)
    other, actor, user, foreign_user, dept, foreign_dept, address, role, group = (
        uuid7() for _ in range(9)
    )
    with unfiltered():
        session.add_all(
            [
                build_company(tenant_id=tenant_a, company_id=other, code="SECOND"),
                build_user(tenant_id=tenant_a, user_id=actor, email="actor@example.test"),
                build_user(tenant_id=tenant_a, user_id=user, email="target@example.test"),
                build_user(tenant_id=tenant_b, user_id=foreign_user),
                build_role(tenant_id=tenant_a, role_id=role, key="review_role"),
                build_user_group(tenant_id=tenant_a, group_id=group),
            ]
        )
        await session.flush()
        session.add_all(
            [
                build_department(tenant_id=tenant_a, company_id=ca, department_id=dept),
                build_department(tenant_id=tenant_b, company_id=cb, department_id=foreign_dept),
                build_company_address(tenant_id=tenant_b, company_id=cb, id=address),
                build_role_permission(
                    tenant_id=tenant_a, role_id=role, permission_key="unit.manage"
                ),
                build_role_assignment(
                    tenant_id=tenant_a, role_id=role, subject_id=group, subject_type="user_group"
                ),
            ]
        )
        await session.commit()
    return Review(
        tenant_a,
        tenant_b,
        ca,
        other,
        cb,
        actor,
        user,
        foreign_user,
        dept,
        foreign_dept,
        address,
        role,
        group,
    )


async def audits(session: AsyncSession, review: Review) -> list[Outbox]:
    with tenant_scope(review.tenant):
        return [r for r in await session.scalars(select(Outbox)) if "action" in r.payload]


@pytest.mark.parametrize("self_add", [True, False])
async def test_b01_privileged_group_requires_assignment_authority(
    client: httpx.AsyncClient,
    review: Review,
    self_add: bool,
) -> None:
    r = await client.post(
        f"/v1/user-groups/{review.group}/members",
        headers=review.headers("group.manage"),
        json={"user_id": str(review.actor if self_add else review.user)},
    )
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("field", ["default_company_id", "default_department_id"])
async def test_b02_user_defaults_reject_foreign_references(
    client: httpx.AsyncClient,
    review: Review,
    field: str,
) -> None:
    foreign_id = (
        review.foreign_company if field == "default_company_id" else review.foreign_department
    )
    r = await client.patch(
        f"/v1/users/{review.user}",
        headers=review.headers("user.update"),
        json={field: str(foreign_id)},
    )
    assert r.status_code == 422, r.text


async def test_b02_department_head_rejects_foreign_user(
    client: httpx.AsyncClient,
    review: Review,
) -> None:
    r = await client.patch(
        f"/v1/companies/{review.company}/departments/{review.department}",
        headers=review.headers("department.manage"),
        json={"head_user_id": str(review.foreign_user)},
    )
    assert r.status_code == 422, r.text


async def test_b02_registration_rejects_foreign_address(
    client: httpx.AsyncClient,
    review: Review,
) -> None:
    r = await client.post(
        f"/v1/companies/{review.company}/tax-registrations",
        headers=review.headers("company.tax_registration.manage"),
        json={
            "tax_system": "gst_in",
            "regime": "regular",
            "number": "27AAPFU0939F1ZV",
            "jurisdiction_code": "MH",
            "valid_from": "2026-04-01",
            "registered_address_id": str(review.foreign_address),
        },
    )
    assert r.status_code == 422, r.text


async def test_b02_assignment_rejects_foreign_company(
    client: httpx.AsyncClient,
    review: Review,
) -> None:
    r = await client.post(
        "/v1/role-assignments",
        headers=review.headers("role.assign", "unit.manage"),
        json={
            "subject_type": "user",
            "subject_id": str(review.user),
            "role_id": str(review.role),
            "scope_type": "company",
            "scope_id": str(review.foreign_company),
        },
    )
    assert r.status_code in (404, 422), r.text


@pytest.mark.parametrize("expired", [True, False])
async def test_b03_role_metadata_checks_scope_and_validity(
    client: httpx.AsyncClient,
    review: Review,
    expired: bool,
) -> None:
    scope = (
        {"valid_to": "2000-02-01"}
        if expired
        else {"scope_type": "company", "scope_id": review.company}
    )
    r = await client.patch(
        f"/v1/roles/{review.role}",
        headers=review.headers("role.manage", **scope),
        json={"name": "Unauthorized rename"},
    )
    assert r.status_code == 403, r.text


async def test_b03_assignment_listing_is_scope_filtered(
    client: httpx.AsyncClient,
    review: Review,
) -> None:
    r = await client.get(
        "/v1/role-assignments",
        headers=review.headers("role.read", scope_type="company", scope_id=review.company),
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


async def test_b12_department_manager_can_update_own_department(
    client: httpx.AsyncClient,
    review: Review,
) -> None:
    r = await client.patch(
        f"/v1/companies/{review.company}/departments/{review.department}",
        headers=review.headers(
            "department.manage", scope_type="department", scope_id=review.department
        ),
        json={"name": "Authorized rename"},
    )
    assert r.status_code == 200, r.text


async def policy(session: AsyncSession, review: Review, field: str, access: str) -> None:
    with tenant_scope(review.tenant):
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_id=review.actor,
                subject_type="user",
                entity_type="identity.company",
                field_key=field,
                access=access,
            )
        )
        await session.commit()


async def test_b04_write_deny_is_enforced_on_diff(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    await policy(session, review, "display_name", "write")
    path = f"/v1/companies/{review.company}"
    h = review.headers("company.read", "company.update")
    current = (await client.get(path, headers=h)).json()["display_name"]
    assert (await client.patch(path, headers=h, json={"display_name": current})).status_code == 200
    r = await client.patch(path, headers=h, json={"display_name": "Denied change"})
    assert r.status_code == 403, r.text


async def test_b04_read_deny_removes_field(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    await policy(session, review, "signatory_name", "read")
    r = await client.get(f"/v1/companies/{review.company}", headers=review.headers("company.read"))
    assert r.status_code == 200, r.text
    assert "signatory_name" not in r.json()


async def test_b04_denied_sort_cannot_leak_values(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    await policy(session, review, "display_name", "read")
    r = await client.get("/v1/companies?sort=display_name", headers=review.headers("company.read"))
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("operation", ["group", "department", "membership", "identity", "tax_read"])
async def test_b05_required_actions_emit_audit(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
    operation: str,
) -> None:
    before = len(await audits(session, review))
    if operation == "group":
        r = await client.post(
            "/v1/user-groups",
            headers=review.headers("group.manage"),
            json={"code": "new_group", "name": "New group"},
        )
    elif operation == "department":
        r = await client.patch(
            f"/v1/companies/{review.company}/departments/{review.department}",
            headers=review.headers("department.manage"),
            json={"name": "Renamed"},
        )
    elif operation == "membership":
        r = await client.post(
            f"/v1/companies/{review.company}/memberships",
            headers=review.headers("department.manage"),
            json={"user_id": str(review.user)},
        )
    elif operation == "identity":
        r = await client.post(
            f"/v1/users/{review.user}/identities",
            headers=review.headers("user.update"),
            json={"provider": "google", "provider_sub": "synthetic-subject"},
        )
    else:
        r = await client.get(
            f"/v1/companies/{review.company}/tax-registrations",
            headers=review.headers("company.read"),
        )
    if operation == "identity":
        # GP2 now requires fresh provider ownership; profile editors cannot bind subjects.
        assert r.status_code == 403
        assert len(await audits(session, review)) == before
    else:
        assert r.status_code in (200, 201), r.text
        assert len(await audits(session, review)) == before + 1


async def test_b06_audit_does_not_capture_personal_values(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    r = await client.patch(
        f"/v1/users/{review.user}",
        headers=review.headers("user.update"),
        json={"phone": "9999900000", "first_name": "Synthetic private name"},
    )
    assert r.status_code == 200, r.text
    payload = json.dumps([row.payload for row in await audits(session, review)])
    assert "9999900000" not in payload and "Synthetic private name" not in payload
    assert "first_name" in payload and "phone" in payload


async def test_b07_company_audit_has_company_scope(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    r = await client.patch(
        f"/v1/companies/{review.company}",
        headers=review.headers("company.update"),
        json={"display_name": "New label"},
    )
    assert r.status_code == 200, r.text
    event = next(
        row for row in await audits(session, review) if row.event_type == "company.updated"
    )
    assert event.payload.get("company_id") == str(review.company)


async def assign(client: httpx.AsyncClient, review: Review, **extra: Any) -> httpx.Response:
    return await client.post(
        "/v1/role-assignments",
        headers=review.headers("role.assign", "unit.manage"),
        json={
            "subject_type": "user",
            "subject_id": str(review.user),
            "role_id": str(review.role),
            "scope_type": "tenant",
            **extra,
        },
    )


async def test_b08_regrant_and_replay_preserve_identity(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    r = await assign(client, review)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    h = review.headers("role.assign", "unit.manage")
    assert (await client.post(f"/v1/role-assignments/{aid}/revoke", headers=h)).status_code == 200
    h["Idempotency-Key"] = "review-regrant"
    path = f"/v1/role-assignments/{aid}/regrant"
    body = {"valid_from": "2026-09-12", "reason": "Access restored"}
    r = await client.post(path, headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == aid and r.json()["is_active"]
    replay = await client.post(path, headers=h, json=body)
    assert replay.status_code == 200 and replay.json() == r.json()
    events = [
        row
        for row in await audits(session, review)
        if row.event_type == "role_assignment.regranted"
    ]
    assert len(events) == 1


async def test_b09_assignment_rejects_reversed_dates(
    client: httpx.AsyncClient, review: Review
) -> None:
    r = await assign(client, review, valid_from="2026-09-12", valid_to="2026-01-01")
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("second_company", [False, True])
async def test_b10_membership_duplicate_and_primary_conflicts(
    client: httpx.AsyncClient,
    review: Review,
    second_company: bool,
) -> None:
    h = review.headers("department.manage")
    body = {"user_id": str(review.user), "is_primary": True}
    assert (
        await client.post(f"/v1/companies/{review.company}/memberships", headers=h, json=body)
    ).status_code == 201
    company = review.other_company if second_company else review.company
    r = await client.post(f"/v1/companies/{company}/memberships", headers=h, json=body)
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("change", ["sort", "search", "tenant"])
async def test_b11_cursor_rejects_changed_context(
    client: httpx.AsyncClient,
    review: Review,
    change: str,
) -> None:
    h = review.headers("company.read")
    r = await client.get("/v1/companies?limit=1&sort=code", headers=h)
    cursor = r.json()["page"]["next_cursor"]
    assert cursor
    params = {"limit": 1, "sort": "code", "cursor": cursor}
    if change == "sort":
        params["sort"] = "display_name"
    if change == "search":
        params["q"] = "Alpha"
    if change == "tenant":
        h = actor_headers(
            tenant_id=review.foreign, user_id=review.foreign_user, grants=[grant(["company.read"])]
        )
    r = await client.get("/v1/companies", params=params, headers=h)
    assert r.status_code == 422, r.text


async def test_b13_groups_are_paginated(
    client: httpx.AsyncClient,
    session: AsyncSession,
    review: Review,
) -> None:
    with tenant_scope(review.tenant):
        session.add(build_user_group(tenant_id=review.tenant, code="second_group"))
        await session.commit()
    r = await client.get("/v1/user-groups?limit=1", headers=review.headers("group.read"))
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), dict)
    assert len(r.json()["items"]) == 1 and r.json()["page"]["has_more"]


@pytest.mark.parametrize("query", ["statuz=inactive", "status=nonsense", "limit=201"])
async def test_b14_bad_queries_use_shared_error(
    client: httpx.AsyncClient,
    review: Review,
    query: str,
) -> None:
    r = await client.get(f"/v1/companies?{query}", headers=review.headers("company.read"))
    assert r.status_code == 422, r.text
    assert "error" in r.json()


async def test_b14_required_patch_field_cannot_be_null(
    client: httpx.AsyncClient, review: Review
) -> None:
    r = await client.patch(
        f"/v1/users/{review.user}", headers=review.headers("user.update"), json={"first_name": None}
    )
    assert r.status_code == 422, r.text


async def test_b15_saved_preferences_are_readable(
    client: httpx.AsyncClient, review: Review
) -> None:
    body = {"theme": "dark", "date_format": "yyyy-MM-dd", "landing_page": "/reports"}
    h = review.headers("user.update", "user.read")
    assert (await client.patch(f"/v1/users/{review.user}", headers=h, json=body)).status_code == 200
    r = await client.get(f"/v1/users/{review.user}", headers=h)
    for key, value in body.items():
        assert r.json().get(key) == value


@pytest.mark.parametrize("subject", ["user", "user_group", "role"])
async def test_policy_subjects_and_scope_precedence(client, session, review, subject):
    from tests.factories import build_user_group_member

    with tenant_scope(review.tenant):
        if subject != "user":
            session.add(
                build_user_group_member(
                    tenant_id=review.tenant, user_group_id=review.group, user_id=review.actor
                )
            )
        subject_id = {"user": review.actor, "user_group": review.group, "role": review.role}[
            subject
        ]
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type=subject,
                subject_id=subject_id,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
            )
        )
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user",
                subject_id=review.actor,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
                effect="allow",
                scope_type="company",
                scope_id=review.company,
            )
        )
        await session.commit()
    h = review.headers("company.read")
    own = await client.get(f"/v1/companies/{review.company}", headers=h)
    other = await client.get(f"/v1/companies/{review.other_company}", headers=h)
    assert own.status_code == other.status_code == 200
    assert "signatory_name" in own.json() and "signatory_name" not in other.json()


async def test_conditional_policy_blocks_transition_and_query(client, session, review):
    with tenant_scope(review.tenant):
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user",
                subject_id=review.actor,
                entity_type="identity.company",
                field_key="display_name",
                access="write",
                condition={"field": "country_code", "cmp": "eq", "value": "IN"},
            )
        )
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user",
                subject_id=review.actor,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
                condition={"field": "amount_precision", "cmp": "gte", "value": "2"},
            )
        )
        await session.commit()
    h = review.headers("company.read", "company.update")
    path = f"/v1/companies/{review.company}"
    result = await client.get(path, headers=h)
    assert result.status_code == 200 and "signatory_name" not in result.json()
    result = await client.patch(path, headers=h, json={"display_name": "Denied"})
    assert result.status_code == 403
    listed = await client.get("/v1/companies", headers=h)
    assert listed.status_code == 200


@pytest.mark.parametrize(
    "condition", [{"invalid": True}, {"field": "no_such_field", "cmp": "eq", "value": 1}]
)
async def test_bad_stored_policy_fails_closed(client, session, review, condition):
    with tenant_scope(review.tenant):
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user",
                subject_id=review.actor,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
                condition=condition,
            )
        )
        await session.commit()
    result = await client.get(
        f"/v1/companies/{review.company}", headers=review.headers("company.read")
    )
    assert result.status_code == 403


async def test_field_policy_create_visibility_and_sparse_list(client, session, review):
    from tests.test_api_companies import _valid_company_body

    await policy(session, review, "display_name", "write")
    result = await client.post(
        "/v1/companies", headers=review.headers("company.create"), json=_valid_company_body("NEW")
    )
    assert result.status_code == 403
    await policy(session, review, "visibility", "write")
    result = await client.post(
        f"/v1/companies/{review.company}/visibility?visibility=unlisted",
        headers=review.headers("company.visibility.manage"),
    )
    assert result.status_code == 403
    await policy(session, review, "display_name", "read")
    result = await client.get("/v1/companies", headers=review.headers("company.read"))
    assert result.status_code == 200 and all(
        "display_name" not in row for row in result.json()["items"]
    )
    result = await client.get("/v1/companies?q=Acme", headers=review.headers("company.read"))
    assert result.status_code == 403


async def test_cursor_normalization_authority_and_policy_changes(client, session, review):
    h = review.headers("company.read")
    first = await client.get("/v1/companies?limit=1", headers=h)
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(
        "/v1/companies",
        params={"cursor": cursor, "sort": "-updated_at", "include_unlisted": "false"},
        headers=h,
    )
    assert second.status_code == 200, second.text
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    changed = await client.get(
        "/v1/companies",
        params={"cursor": cursor},
        headers=review.headers("company.read", "company.update"),
    )
    assert changed.status_code == 422
    await policy(session, review, "signatory_name", "read")
    changed = await client.get("/v1/companies", params={"cursor": cursor}, headers=h)
    assert changed.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "status=unknown",
        "user_type=unknown",
        "limit=0",
        "q=x",
        "sort=email&sort=display_name",
        "extra=true",
    ],
)
async def test_user_query_validation_is_strict(client, review, query):
    r = await client.get("/v1/users?" + query, headers=review.headers("user.read"))
    assert r.status_code == 422 and "error" in r.json()


@pytest.mark.parametrize(
    "path,permission,field",
    [
        ("/v1/companies/{company}", "company.update", "display_name"),
        ("/v1/companies/{company}/departments/{department}", "department.manage", "name"),
        ("/v1/roles/{role}", "role.manage", "permissions"),
        ("/v1/tenant", "tenant.update", "name"),
    ],
)
async def test_required_patch_nulls_are_input_errors(client, review, path, permission, field):
    from dataclasses import asdict

    r = await client.patch(
        path.format(**asdict(review)), headers=review.headers(permission), json={field: None}
    )
    assert r.status_code == 422, r.text


async def test_display_config_merges_only_presentation_preferences(client, session, review):
    h = review.headers("user.update", "company.read")
    updated = await client.patch(
        f"/v1/users/{review.actor}",
        headers=h,
        json={
            "locale": "en-GB",
            "timezone": "Europe/London",
            "date_format": "yyyy-MM-dd",
            "currency_display": "code",
        },
    )
    assert updated.status_code == 200
    r = await client.get(f"/v1/companies/{review.company}/display-config", headers=h)
    assert r.status_code == 200 and r.json()["currency_display"] == "code"
    assert r.json()["locale"] == "en-GB" and r.json()["amount_precision"] == 2
    await policy(session, review, "locale", "read")
    r = await client.get(f"/v1/companies/{review.company}/display-config", headers=h)
    assert "locale" not in r.json()


async def test_regrant_replay_reauthorizes_and_rejects_changed_body(client, session, review):
    granted = await assign(client, review)
    aid = granted.json()["id"]
    h = review.headers("role.assign", "unit.manage")
    assert (await client.post(f"/v1/role-assignments/{aid}/revoke", headers=h)).status_code == 200
    path = f"/v1/role-assignments/{aid}/regrant"
    body = {"reason": "Restoration"}
    r = await client.post(path, headers=h, json=body)
    assert r.status_code == 422
    h["Idempotency-Key"] = "review-authority-replay"
    assert (await client.post(path, headers=h, json=body)).status_code == 200
    reduced = review.headers("role.assign") | {"Idempotency-Key": h["Idempotency-Key"]}
    assert (await client.post(path, headers=reduced, json=body)).status_code == 403
    assert (
        await client.post(path, headers=h, json={"reason": "Changed request"})
    ).status_code == 422
    h["Idempotency-Key"] = "different-command"
    assert (await client.post(path, headers=h, json=body)).status_code == 409


async def test_department_ancestor_grants_do_not_reach_siblings(client, session, review):
    child, sibling = uuid7(), uuid7()
    with tenant_scope(review.tenant):
        session.add_all(
            [
                build_department(
                    tenant_id=review.tenant,
                    company_id=review.company,
                    department_id=child,
                    code="CHILD",
                    parent_id=review.department,
                    path=f"/{review.department.hex}/{child.hex}/",
                ),
                build_department(
                    tenant_id=review.tenant,
                    company_id=review.company,
                    department_id=sibling,
                    code="SIBLING",
                ),
            ]
        )
        await session.commit()
    h = review.headers(
        "department.manage", "department.read", scope_type="department", scope_id=review.department
    )
    root = f"/v1/companies/{review.company}/departments"
    assert (
        await client.patch(f"{root}/{child}", headers=h, json={"name": "Allowed"})
    ).status_code == 200
    assert (
        await client.patch(f"{root}/{sibling}", headers=h, json={"name": "Denied"})
    ).status_code == 403
    listing = await client.get(root, headers=h)
    assert {r["id"] for r in listing.json()["items"]} == {str(child), str(review.department)}
    r = await client.post(f"{root}/{child}/reparent", headers=h, json={"parent_id": str(sibling)})
    assert r.status_code == 403


async def test_group_join_requires_authority_for_future_grants(client, session, review):
    import datetime as dt

    from identity.models import RoleAssignment

    with tenant_scope(review.tenant):
        assigned = await session.scalar(
            select(RoleAssignment).where(RoleAssignment.subject_id == review.group)
        )
        assigned.valid_from = dt.date(2099, 1, 1)
        await session.commit()
    path = f"/v1/user-groups/{review.group}/members"
    r = await client.post(
        path, headers=review.headers("group.manage"), json={"user_id": str(review.user)}
    )
    assert r.status_code == 403
    r = await client.post(
        path,
        headers=review.headers("group.manage", "role.assign", "unit.manage"),
        json={"user_id": str(review.user)},
    )
    assert r.status_code == 201, r.text


@pytest.mark.parametrize(
    "resource,permission",
    [
        ("memberships", "department.read"),
        ("tax-registrations", "company.read"),
        ("licences", "company.read"),
        ("statutory-ids", "company.read"),
        ("addresses", "company.read"),
    ],
)
async def test_child_lists_have_bounded_envelopes(client, review, resource, permission):
    path = f"/v1/companies/{review.company}/{resource}"
    r = await client.get(path, headers=review.headers(permission))
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"items", "page"} and not r.json()["page"]["has_more"]
    assert (
        await client.get(path + "?limit=201", headers=review.headers(permission))
    ).status_code == 422


async def test_identity_list_cursor_stays_with_user(client, session, review):
    h = review.headers("user.update", "user.read")
    root = f"/v1/users/{review.user}/identities"
    from tests.factories import build_user_identity

    with tenant_scope(review.tenant):
        for i in range(3):
            session.add(
                build_user_identity(
                    tenant_id=review.tenant, user_id=review.user, provider_sub=f"review-sub-{i}"
                )
            )
        await session.commit()
    seen = []
    cursor = None
    for _ in range(3):
        r = await client.get(
            root, headers=h, params={"limit": 1, **({"cursor": cursor} if cursor else {})}
        )
        assert r.status_code == 200, r.text
        seen.extend(item["id"] for item in r.json()["items"])
        cursor = r.json()["page"]["next_cursor"]
        if cursor:
            other = await client.get(
                f"/v1/users/{review.actor}/identities", headers=h, params={"cursor": cursor}
            )
            assert other.status_code == 422
    assert len(set(seen)) == 3 and cursor is None


@pytest.mark.parametrize("self_join", [True, False])
async def test_group_field_allow_requires_policy_authority(client, session, review, self_join):
    group = uuid7()
    with tenant_scope(review.tenant):
        session.add(build_user_group(tenant_id=review.tenant, group_id=group, code="policy_group"))
        await session.flush()
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user_group",
                subject_id=group,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
                effect="allow",
                scope_type="company",
                scope_id=review.company,
            )
        )
        await session.commit()
    path = f"/v1/user-groups/{group}/members"
    body = {"user_id": str(review.actor if self_join else review.user)}
    response = await client.post(path, headers=review.headers("group.manage"), json=body)
    assert response.status_code == 403
    if not self_join:
        response = await client.post(
            path, headers=review.headers("group.manage", "field_policy.manage"), json=body
        )
        assert response.status_code == 403
        response = await client.post(
            path,
            headers=review.headers("group.manage", "field_policy.manage", "company.read"),
            json=body,
        )
        assert response.status_code == 201


async def test_default_affiliations_merge_and_clear_consistently(client, review):
    path = f"/v1/users/{review.user}"
    headers = review.headers("user.update")
    response = await client.patch(
        path,
        headers=headers,
        json={
            "default_company_id": str(review.company),
            "default_department_id": str(review.department),
        },
    )
    assert response.status_code == 200, response.text
    assert (
        await client.patch(
            path, headers=headers, json={"default_company_id": str(review.other_company)}
        )
    ).status_code == 422
    assert (
        await client.patch(path, headers=headers, json={"default_company_id": None})
    ).status_code == 422
    response = await client.patch(
        path, headers=headers, json={"default_company_id": None, "default_department_id": None}
    )
    assert response.status_code == 200 and response.json()["default_department_id"] is None


async def test_tenant_contacts_are_redacted_and_request_errors_hide_input(client, session, review):
    response = await client.patch(
        "/v1/tenant",
        headers=review.headers("tenant.update"),
        json={
            "primary_contact_email": "private-contact@example.test",
            "name": "Private contact label",
        },
    )
    assert response.status_code == 200, response.text
    payload = json.dumps([row.payload for row in await audits(session, review)])
    assert "private-contact@example.test" not in payload and "Private contact label" not in payload
    assert "primary_contact_email" in payload
    response = await client.patch(
        "/v1/tenant",
        headers=review.headers("tenant.update"),
        json={"primary_contact_email": "sensitive-invalid-input"},
    )
    assert response.status_code == 422 and "sensitive-invalid-input" not in response.text
    assert "body.primary_contact_email" in response.json()["error"]["fields"]


@pytest.mark.parametrize("inactive", ["company", "department", "role", "subject"])
async def test_assignments_cannot_select_inactive_objects(client, session, review, inactive):
    from identity.models import Company, Department, Role, User

    with tenant_scope(review.tenant):
        model, object_id = {
            "company": (Company, review.company),
            "department": (Department, review.department),
            "role": (Role, review.role),
            "subject": (User, review.user),
        }[inactive]
        row = await session.get(model, object_id)
        if inactive == "company":
            row.status = "closed"
        elif inactive == "subject":
            row.status = "deactivated"
        else:
            row.is_active = False
        await session.commit()
    result = await assign(client, review, scope_type="department", scope_id=str(review.department))
    assert result.status_code == 422, result.text


@pytest.mark.parametrize(
    "scope_type,scope_id",
    [
        ("tenant", "random"),
        ("company", None),
        ("company", "zero"),
        ("company", "random"),
        ("department", "random"),
        ("nonsense", None),
    ],
)
async def test_assignment_scope_requires_an_existing_real_object(
    client, review, scope_type, scope_id
):
    value = (
        str(uuid7())
        if scope_id == "random"
        else str(uuid.UUID(int=0))
        if scope_id == "zero"
        else None
    )
    response = await assign(client, review, scope_type=scope_type, scope_id=value)
    assert response.status_code == 422, response.text


async def test_assignment_lists_respect_department_and_company_scope(client, session, review):
    from tests.api_support import actor_headers, grant

    with tenant_scope(review.tenant):
        session.add_all(
            [
                build_role_assignment(
                    tenant_id=review.tenant,
                    role_id=review.role,
                    subject_id=review.user,
                    scope_type="department",
                    scope_id=review.department,
                ),
                build_role_assignment(
                    tenant_id=review.tenant,
                    role_id=review.role,
                    subject_id=review.user,
                    scope_type="company",
                    scope_id=review.company,
                ),
                build_role_assignment(
                    tenant_id=review.tenant,
                    role_id=review.role,
                    subject_id=review.user,
                    scope_type="company",
                    scope_id=review.other_company,
                ),
            ]
        )
        await session.commit()
    for scope, scope_id, expected in [
        ("department", review.department, 1),
        ("company", review.company, 2),
    ]:
        h = review.headers("role.read", scope_type=scope, scope_id=scope_id)
        response = await client.get("/v1/role-assignments", headers=h)
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == expected
    headers = actor_headers(
        tenant_id=review.tenant,
        user_id=review.actor,
        grants=[
            grant(
                ["role.read"], scope_type="company", scope_id=review.company, valid_to="2001-01-01"
            ),
            grant(["role.read"], scope_type="company", scope_id=review.other_company),
            grant(["company.read"]),
        ],
    )
    response = await client.get("/v1/role-assignments", headers=headers)
    assert response.status_code == 200 and len(response.json()["items"]) == 1
    assert response.json()["items"][0]["scope_id"] == str(review.other_company)


async def test_revoked_assignment_does_not_bypass_scope_on_repeat(client, review):
    response = await assign(client, review)
    path = f"/v1/role-assignments/{response.json()['id']}/revoke"
    full = review.headers("role.assign", "unit.manage")
    assert (await client.post(path, headers=full)).status_code == 200
    assert (await client.post(path, headers=full)).status_code == 200
    narrow = review.headers(
        "role.assign", "unit.manage", scope_type="company", scope_id=review.company
    )
    assert (await client.post(path, headers=narrow)).status_code == 403


async def test_default_assignment_dates_and_cross_midnight_replay(client, review, monkeypatch):
    import datetime as dt

    from identity.api import roles

    today = dt.datetime.now(dt.UTC).date()
    response = await assign(client, review, valid_to=(today - dt.timedelta(days=1)).isoformat())
    assert response.status_code == 422
    response = await assign(client, review)
    aid = response.json()["id"]
    headers = review.headers("role.assign", "unit.manage")
    assert (
        await client.post(f"/v1/role-assignments/{aid}/revoke", headers=headers)
    ).status_code == 200
    headers["Idempotency-Key"] = "midnight-replay"
    path = f"/v1/role-assignments/{aid}/regrant"
    body = {"reason": "Short restoration", "valid_to": today.isoformat()}
    original = await client.post(path, headers=headers, json=body)
    assert original.status_code == 200, original.text
    tomorrow = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    monkeypatch.setattr(roles, "utcnow", lambda: tomorrow)
    replay = await client.post(path, headers=headers, json=body)
    assert replay.status_code == 200 and replay.json() == original.json()


async def test_regrant_missing_and_self_assignment_fail(client, session, review):
    h = review.headers("role.assign", "unit.manage") | {"Idempotency-Key": "missing-grant"}
    response = await client.post(
        f"/v1/role-assignments/{uuid7()}/regrant", headers=h, json={"reason": "Missing"}
    )
    assert response.status_code == 404
    with tenant_scope(review.tenant):
        own = build_role_assignment(
            tenant_id=review.tenant, role_id=review.role, subject_id=review.actor, is_active=False
        )
        session.add(own)
        await session.commit()
        aid = own.id
    h["Idempotency-Key"] = "self-grant"
    response = await client.post(
        f"/v1/role-assignments/{aid}/regrant", headers=h, json={"reason": "Self"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("field", ["unregistered_field", "id"])
async def test_unsupported_policy_fields_do_not_silently_allow_access(
    client, session, review, field
):
    await policy(session, review, field, "read")
    response = await client.get(
        f"/v1/companies/{review.company}", headers=review.headers("company.read")
    )
    assert response.status_code == 403


async def test_conditional_allow_does_not_override_deny_for_unrestricted_query(
    client, session, review
):
    from tests.factories import build_user_group_member

    with tenant_scope(review.tenant):
        session.add(
            build_user_group_member(
                tenant_id=review.tenant, user_group_id=review.group, user_id=review.actor
            )
        )
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user",
                subject_id=review.actor,
                entity_type="identity.company",
                field_key="display_name",
                access="read",
            )
        )
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user_group",
                subject_id=review.group,
                entity_type="identity.company",
                field_key="display_name",
                access="read",
                effect="allow",
                condition={"field": "code", "cmp": "eq", "value": "SECOND"},
                scope_type="company",
                scope_id=review.other_company,
            )
        )
        await session.commit()
    response = await client.get(
        "/v1/companies?sort=display_name", headers=review.headers("company.read")
    )
    assert response.status_code == 403
    response = await client.get(
        f"/v1/companies/{review.other_company}", headers=review.headers("company.read")
    )
    assert response.status_code == 200 and "display_name" in response.json()
    response = await client.get(
        f"/v1/companies/{review.company}", headers=review.headers("company.read")
    )
    assert response.status_code == 200 and "display_name" not in response.json()


async def test_unknown_tenant_cannot_begin_mutation(client):
    headers = actor_headers(tenant_id=uuid7(), user_id=uuid7(), grants=[grant(["group.manage"])])
    response = await client.post(
        "/v1/user-groups", headers=headers, json={"code": "example", "name": "Example"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/not-a-uuid/", "/00000000000000000000000000000001/"])
async def test_corrupt_department_ancestry_returns_controlled_error(client, session, review, path):
    from identity.models import Department

    with tenant_scope(review.tenant):
        row = await session.get(Department, review.department)
        row.path = path
        await session.commit()
    response = await client.patch(
        f"/v1/companies/{review.company}/departments/{review.department}",
        headers=review.headers("department.manage"),
        json={"name": "Requires repair"},
    )
    assert response.status_code == 422


async def test_group_regrant_uses_current_database_membership(client, session, review):
    from identity.models import RoleAssignment
    from tests.factories import build_user_group_member

    with tenant_scope(review.tenant):
        row = await session.scalar(
            select(RoleAssignment).where(RoleAssignment.subject_id == review.group)
        )
        aid = row.id
    headers = review.headers("role.assign", "unit.manage")
    assert (
        await client.post(f"/v1/role-assignments/{aid}/revoke", headers=headers)
    ).status_code == 200
    headers["Idempotency-Key"] = "restore-group"
    path = f"/v1/role-assignments/{aid}/regrant"
    assert (
        await client.post(path, headers=headers, json={"reason": "Restore group"})
    ).status_code == 200
    with tenant_scope(review.tenant):
        session.add(
            build_user_group_member(
                tenant_id=review.tenant, user_group_id=review.group, user_id=review.actor
            )
        )
        await session.commit()
    # Even replay must notice membership omitted from the signed context.
    assert (
        await client.post(path, headers=headers, json={"reason": "Restore group"})
    ).status_code == 403


async def test_role_field_policy_is_limited_to_assignment_scope(client, session, review):
    with tenant_scope(review.tenant):
        session.add(
            build_role_assignment(
                tenant_id=review.tenant,
                role_id=review.role,
                subject_id=review.actor,
                scope_type="company",
                scope_id=review.company,
            )
        )
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="role",
                subject_id=review.role,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
            )
        )
        await session.commit()
    headers = review.headers("company.read")
    own = await client.get(f"/v1/companies/{review.company}", headers=headers)
    other = await client.get(f"/v1/companies/{review.other_company}", headers=headers)
    assert own.status_code == other.status_code == 200
    assert "signatory_name" not in own.json() and "signatory_name" in other.json()


async def test_department_scoped_reader_cannot_list_other_company(client, review):
    headers = review.headers("department.read", scope_type="department", scope_id=review.department)
    response = await client.get(
        f"/v1/companies/{review.other_company}/departments", headers=headers
    )
    assert response.status_code == 200 and response.json()["items"] == []


async def test_tax_registration_amendment_rechecks_address_ownership(client, session, review):
    from tests.factories import build_company_tax_registration

    with tenant_scope(review.tenant):
        row = build_company_tax_registration(tenant_id=review.tenant, company_id=review.company)
        session.add(row)
        await session.commit()
        rid = row.id
    path = f"/v1/companies/{review.company}/tax-registrations/{rid}"
    headers = review.headers("company.tax_registration.manage")
    response = await client.patch(
        path, headers=headers, json={"registered_address_id": str(review.foreign_address)}
    )
    assert response.status_code == 422
    response = await client.patch(path, headers=headers, json={"jurisdiction_code": None})
    assert response.status_code == 422


async def test_failed_identity_insert_rolls_back_its_audit(client, session, review):
    path = f"/v1/users/{review.user}/identities"
    headers = review.headers("user.update")
    body = {"provider": "google", "provider_sub": "transactional-audit-test"}
    # Fresh verified ownership is tested with RSA tokens in test_gap_identity_links.
    # A profile editor's attempted binding must also leave the audit unchanged.
    before = len(await audits(session, review))
    assert (await client.post(path, headers=headers, json=body)).status_code == 403
    assert len(await audits(session, review)) == before


async def test_denied_field_change_leaves_data_and_outbox_unchanged(client, session, review):
    from identity.models import Company

    await policy(session, review, "display_name", "write")
    with tenant_scope(review.tenant):
        row = await session.get(Company, review.company)
        original = row.display_name
    before = len(await audits(session, review))
    response = await client.patch(
        f"/v1/companies/{review.company}",
        headers=review.headers("company.update"),
        json={"display_name": "Forbidden label"},
    )
    assert response.status_code == 403
    with tenant_scope(review.tenant):
        await session.refresh(row)
        assert row.display_name == original
    assert len(await audits(session, review)) == before


async def test_inactive_group_cannot_supply_field_allow(client, session, review):
    from identity.models import UserGroup
    from tests.factories import build_user_group_member

    await policy(session, review, "signatory_name", "read")
    with tenant_scope(review.tenant):
        group = await session.get(UserGroup, review.group)
        group.is_active = False
        session.add(
            build_user_group_member(
                tenant_id=review.tenant, user_group_id=review.group, user_id=review.actor
            )
        )
        session.add(
            build_field_policy(
                tenant_id=review.tenant,
                subject_type="user_group",
                subject_id=review.group,
                entity_type="identity.company",
                field_key="signatory_name",
                access="read",
                effect="allow",
                scope_type="company",
                scope_id=review.company,
            )
        )
        await session.commit()
    response = await client.get(
        f"/v1/companies/{review.company}", headers=review.headers("company.read")
    )
    assert response.status_code == 200 and "signatory_name" not in response.json()


async def test_openapi_validation_errors_use_the_runtime_envelope(app):
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        if not path.startswith("/v1/"):
            continue
        for method, operation in operations.items():
            if method not in {"get", "post", "patch"}:
                continue
            error = operation["responses"]["422"]["content"]["application/json"]["schema"]
            assert error.get("$ref", "").endswith("/ErrorEnvelope"), (path, method, error)
